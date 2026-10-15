"""Services de gestion des numéros de contact des entreprises — MLD §4.1.1 (v1.7)."""

import re
from typing import Any

from django.db import transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.exceptions import ValidationError

from apps.audit.services import journaliser
from apps.core.enums import ActionAudit
from apps.tenants.models import TelephoneEntreprise

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
NOMBRE_MAX = 5
SEPARATEURS = re.compile(r"[\s().\-/]")

__all__ = [
    "E164",
    "NOMBRE_MAX",
    "SEPARATEURS",
    "definir_telephone_principal",
    "est_e164",
    "normaliser_telephone",
    "remplacer_telephones",
]


def normaliser_telephone(valeur: str | None) -> str:
    """`+225 07 00-00.00 00` → `+2250700000000` ; `00225…` → `+225…`. N'invente pas d'indicatif."""
    if not valeur:
        return ""
    valeur_nettoyee = SEPARATEURS.sub("", str(valeur).strip())
    if valeur_nettoyee.startswith("00"):
        valeur_nettoyee = "+" + valeur_nettoyee[2:]
    return valeur_nettoyee


def est_e164(valeur: str | None) -> bool:
    """Vérifie si la valeur respecte le format international E.164."""
    return bool(valeur and E164.match(valeur))


def remplacer_telephones(
    entreprise,
    telephones: list[dict[str, Any]],
    *,
    auteur_id=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> list[TelephoneEntreprise]:
    """Remplace la liste des numéros d'une entreprise et recopie le principal
    dans telephone_contact.

    Gère l'écriture dans le schéma public et la journalisation d'audit dans le schéma tenant.
    """
    if not telephones:
        raise ValidationError({"telephones": "Renseignez au moins un numéro de contact."})

    if len(telephones) > NOMBRE_MAX:
        raise ValidationError({"telephones": "Cinq numéros au plus par entreprise."})

    principaux = [
        t for t in telephones if bool(t.get("principal") or t.get("est_principal"))
    ]
    if len(principaux) != 1:
        raise ValidationError({"telephones": "Désignez un, et un seul, numéro principal."})

    numeros_vus = set()
    for t in telephones:
        num = normaliser_telephone(t.get("numero", ""))
        if num in numeros_vus:
            raise ValidationError({"telephones": f"Le numéro {num} figure deux fois."})
        numeros_vus.add(num)

    public_schema = get_public_schema_name()

    with transaction.atomic():
        with schema_context(public_schema):
            # 1. Lire les lignes actives de l'entreprise avec select_for_update
            existants = list(
                TelephoneEntreprise.objects.select_for_update().filter(
                    entreprise=entreprise, supprime_le__isnull=True
                )
            )
            existants_par_id = {str(item.id): item for item in existants}
            # L'état d'avant, figé **avant** toute écriture : les objets de `existants` sont
            # modifiés en place plus bas, et un « avant » relu après coup égalerait l'« après »
            # — une modification de libellé ou de numéro ne serait alors jamais journalisée.
            valeur_avant = [
                {"libelle": item.libelle, "numero": item.numero, "principal": item.est_principal}
                for item in sorted(
                    existants,
                    key=lambda x: (-int(x.est_principal), x.ordre, x.cree_le),
                )
            ]

            for t in telephones:
                tid = t.get("id")
                if tid and str(tid) not in existants_par_id:
                    raise ValidationError(
                        {"telephones": "Numéro introuvable : rechargez la page."}
                    )

            # 2. Retirer d'abord le principal actuel si le principal change
            for item in existants:
                if item.est_principal:
                    item.est_principal = False
                    item.save(update_fields=["est_principal", "modifie_le"])

            # 3. Mettre à jour, créer et supprimer logiquement
            # Réconciliation par ID en priorité, puis par numéro pour les entrées sans ID
            ids_conserves = set()
            resultat: list[TelephoneEntreprise] = []
            a_creer: list[tuple[int, dict]] = []

            # Première passe : réconcilier les existants
            for index, t in enumerate(telephones):
                tid = t.get("id")
                numero = normaliser_telephone(t["numero"])
                libelle = t["libelle"]
                est_principal = bool(t.get("principal") or t.get("est_principal"))

                matched = None
                if tid and str(tid) in existants_par_id:
                    matched = existants_par_id[str(tid)]
                elif not tid:
                    for ex in existants:
                        if str(ex.id) not in ids_conserves and ex.numero == numero:
                            matched = ex
                            break

                if matched:
                    matched.libelle = libelle
                    matched.numero = numero
                    matched.est_principal = est_principal
                    matched.ordre = index
                    matched.save(
                        update_fields=[
                            "libelle",
                            "numero",
                            "est_principal",
                            "ordre",
                            "modifie_le",
                        ]
                    )
                    ids_conserves.add(str(matched.id))
                    resultat.append(matched)
                else:
                    a_creer.append((index, t))

            # Supprimer logiquement les existants non conservés avant de créer
            maintenant = timezone.now()
            for item in existants:
                if str(item.id) not in ids_conserves:
                    item.supprime_le = maintenant
                    item.save(update_fields=["supprime_le", "modifie_le"])

            # Deuxième passe : créer les nouveaux numéros
            for index, t in a_creer:
                libelle = t["libelle"]
                numero = normaliser_telephone(t["numero"])
                est_principal = bool(t.get("principal") or t.get("est_principal"))
                tel_obj = TelephoneEntreprise.objects.create(
                    entreprise=entreprise,
                    libelle=libelle,
                    numero=numero,
                    est_principal=est_principal,
                    ordre=index,
                )
                ids_conserves.add(str(tel_obj.id))
                resultat.append(tel_obj)

            # Trier le résultat selon l'ordre d'entrée
            resultat.sort(key=lambda x: x.ordre)

            # 4. Mettre à jour entreprise.telephone_contact = <numéro principal>
            num_principal = next(
                normaliser_telephone(t["numero"])
                for t in telephones
                if bool(t.get("principal") or t.get("est_principal"))
            )
            if entreprise.telephone_contact != num_principal:
                entreprise.telephone_contact = num_principal
                entreprise.save(update_fields=["telephone_contact"])

        # 5. Journaliser dans le schéma de l'entreprise si quelque chose a changé
        valeur_apres = [
            {
                "libelle": item.libelle,
                "numero": item.numero,
                "principal": item.est_principal,
            }
            for item in resultat
        ]

        if valeur_avant != valeur_apres:
            with schema_context(entreprise.schema_name):
                journaliser(
                    action=ActionAudit.MODIFICATION,
                    type_entite="telephone_entreprise",
                    entite_id=entreprise.pk,
                    utilisateur_id=auteur_id,
                    valeur_avant=valeur_avant,
                    valeur_apres=valeur_apres,
                    adresse_ip=adresse_ip,
                    appareil=appareil,
                )

    return resultat


def definir_telephone_principal(
    entreprise,
    numero: str,
    *,
    auteur_id=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> None:
    """Pour un client qui n'envoie que `telephone_contact` : met à jour (ou crée, libellé
    STANDARD) le numéro principal, en gardant les autres.
    """
    numero_norm = normaliser_telephone(numero)
    if not est_e164(numero_norm):
        raise ValidationError(
            {
                "telephone_contact": (
                    "Saisissez le numéro au format international : + suivi de l'indicatif "
                    "du pays et du numéro, par exemple +225 07 00 00 00 00."
                )
            }
        )

    public_schema = get_public_schema_name()
    with schema_context(public_schema):
        existants = list(
            TelephoneEntreprise.objects.filter(
                entreprise=entreprise, supprime_le__isnull=True
            ).order_by("-est_principal", "ordre", "cree_le")
        )

        principal_existant = next((t for t in existants if t.est_principal), None)

        if principal_existant:
            nouvelle_liste = []
            for t in existants:
                if t.id == principal_existant.id:
                    nouvelle_liste.append(
                        {
                            "id": t.id,
                            "libelle": t.libelle,
                            "numero": numero_norm,
                            "principal": True,
                        }
                    )
                else:
                    nouvelle_liste.append(
                        {
                            "id": t.id,
                            "libelle": t.libelle,
                            "numero": t.numero,
                            "principal": False,
                        }
                    )
        else:
            nouvelle_liste = [
                {
                    "id": None,
                    "libelle": TelephoneEntreprise.Libelle.STANDARD,
                    "numero": numero_norm,
                    "principal": True,
                }
            ]
            for t in existants:
                nouvelle_liste.append(
                    {
                        "id": t.id,
                        "libelle": t.libelle,
                        "numero": t.numero,
                        "principal": False,
                    }
                )

    remplacer_telephones(
        entreprise,
        nouvelle_liste,
        auteur_id=auteur_id,
        adresse_ip=adresse_ip,
        appareil=appareil,
    )

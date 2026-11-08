"""Socle du cloisonnement par entreprise (D9, lot 1) — sans base de données.

Ces tests n'ouvrent aucune connexion : le refus doit tomber **avant** la moindre requête SQL, et
c'est précisément ce qu'ils vérifient. Une requête hors contexte qui atteindrait la base serait
déjà une fuite.
"""

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import models
from rest_framework.exceptions import AuthenticationFailed

from apps.core.authentification import verifier_et_activer
from apps.core.contexte import (
    HorsContexteEntreprise,
    activer_entreprise,
    avec_entreprise,
    contexte_entreprise,
    en_portee_plateforme,
    entreprise_courante_id,
    exiger_entreprise,
    portee_plateforme,
    reinitialiser_contexte,
    verification_plateforme,
)
from apps.core.middleware_contexte import ContexteEntrepriseMiddleware
from apps.core.models import ErreurIsolation, ModeleBase, ModeleEntreprise

A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


class Essai(ModeleEntreprise):
    """Table fictive : jamais créée, seulement compilée."""

    libelle = models.CharField(max_length=20)

    class Meta:
        app_label = "core"
        managed = False
        db_table = "essai_cloisonnement"


@pytest.fixture(autouse=True)
def contexte_vierge():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def sql(requete) -> str:
    return str(requete.query)


# --- Le contexte ---------------------------------------------------------------------------------
class TestContexte:
    def test_rien_par_defaut(self):
        assert entreprise_courante_id() is None
        assert not en_portee_plateforme()
        with pytest.raises(HorsContexteEntreprise):
            exiger_entreprise()

    def test_contexte_ouvert_puis_restaure(self):
        with contexte_entreprise(A):
            assert entreprise_courante_id() == A
            with contexte_entreprise(str(B)):
                assert entreprise_courante_id() == B
            assert entreprise_courante_id() == A
        assert entreprise_courante_id() is None

    def test_accepte_une_instance(self):
        with contexte_entreprise(SimpleNamespace(pk=A)):
            assert exiger_entreprise() == A

    def test_portee_plateforme_exige_un_motif(self):
        with pytest.raises(ValueError), portee_plateforme(motif="  "):
            pass

    def test_portee_plateforme_refusee_dans_une_entreprise(self):
        with (
            contexte_entreprise(A),
            pytest.raises(HorsContexteEntreprise),
            portee_plateforme(motif="élargir"),
        ):
            pass

    def test_entreprise_dans_une_portee_plateforme(self):
        with portee_plateforme(motif="tâche de nuit"):
            assert en_portee_plateforme()
            with contexte_entreprise(A):
                assert not en_portee_plateforme()
                assert entreprise_courante_id() == A
            assert en_portee_plateforme()
        assert not en_portee_plateforme()

    def test_decorateur_de_tache(self):
        vu = {}

        @avec_entreprise
        def tache(entreprise_id, valeur):
            vu["entreprise"] = entreprise_courante_id()
            return valeur * 2

        assert tache(str(A), 21) == 42
        assert vu["entreprise"] == A
        assert entreprise_courante_id() is None

    def test_verification_plateforme_sous_une_entreprise(self):
        # Lot 5 : l'unicité d'une adresse se vérifie sur toute la plateforme, même pendant une
        # requête d'entreprise — puis l'entreprise est rendue.
        with contexte_entreprise(A):
            with verification_plateforme(motif="essai"):
                assert entreprise_courante_id() is None
                assert en_portee_plateforme()
            assert entreprise_courante_id() == A
            assert not en_portee_plateforme()

    def test_verification_plateforme_exige_un_motif(self):
        with pytest.raises(ValueError):
            verification_plateforme(motif=" ").__enter__()

    def test_tache_eager_rend_le_contexte_de_la_requete(self):
        # Lot 5 : en mode eager, la tâche tourne dans le fil de la requête. Elle part sans
        # entreprise, et la requête retrouve la sienne ensuite.
        from config.celery import _contexte_rendu, _contexte_vierge

        with contexte_entreprise(A):
            _contexte_vierge(task_id="t1")
            assert entreprise_courante_id() is None
            _contexte_rendu(task_id="t1")
            assert entreprise_courante_id() == A

    def test_tache_sur_un_travailleur_laisse_un_contexte_vide(self):
        from config.celery import _contexte_rendu, _contexte_vierge

        _contexte_vierge(task_id="t2")
        activer_entreprise(B)  # une tâche qui active sans refermer
        _contexte_rendu(task_id="t2")
        assert entreprise_courante_id() is None


# --- Les gestionnaires ---------------------------------------------------------------------------
class TestGestionnaires:
    @pytest.mark.parametrize("gestionnaire", ["objects", "tous_objets"])
    @pytest.mark.parametrize(
        "evaluer",
        [list, lambda q: q.count(), lambda q: q.exists(), lambda q: q.first(),
         lambda q: q.update(libelle="x"), lambda q: q.aggregate(n=models.Count("id")),
         lambda q: list(q.iterator()), lambda q: list(q.values_list("id"))],
        ids=["list", "count", "exists", "first", "update", "aggregate", "iterator", "values"],
    )
    def test_hors_contexte_refuse_avant_la_base(self, gestionnaire, evaluer):
        requete = getattr(Essai, gestionnaire).all()
        with (
            mock.patch("django.db.backends.utils.CursorWrapper.execute") as execute,
            pytest.raises(HorsContexteEntreprise),
        ):
            evaluer(requete)
        execute.assert_not_called()

    @pytest.mark.parametrize("gestionnaire", ["objects", "tous_objets"])
    def test_dans_un_contexte_filtre_tout_de_suite(self, gestionnaire):
        with contexte_entreprise(A):
            requete = getattr(Essai, gestionnaire).filter(libelle="x")
        assert '"entreprise_id" =' in sql(requete)
        assert A.hex in sql(requete).replace("-", "")

    def test_cree_hors_contexte_filtre_a_l_evaluation(self):
        requete = Essai.objects.all()  # comme un queryset de champ de serializer
        assert '"entreprise_id" =' not in sql(requete)
        with contexte_entreprise(B):
            requete._cloisonner()
        assert B.hex in sql(requete).replace("-", "")

    def test_cloisonnement_conserve_par_les_clones(self):
        requete = Essai.objects.all().filter(libelle="x").order_by("libelle")
        with pytest.raises(HorsContexteEntreprise):
            list(requete)

    def test_portee_plateforme_ne_filtre_pas(self):
        with portee_plateforme(motif="statistiques"):
            requete = Essai.objects.all()
        assert '"entreprise_id" =' not in sql(requete)

    def test_objects_exclut_toujours_les_supprimes(self):
        with contexte_entreprise(A):
            assert '"supprime_le" IS NULL' in sql(Essai.objects.all())
            assert '"supprime_le" IS NULL' not in sql(Essai.tous_objets.all())


# --- L'enregistrement ----------------------------------------------------------------------------
class TestEnregistrement:
    @pytest.fixture(autouse=True)
    def sans_base(self):
        with mock.patch.object(ModeleBase, "save") as save:
            yield save

    def test_entreprise_remplie_depuis_le_contexte(self):
        ligne = Essai(libelle="x")
        with contexte_entreprise(A):
            ligne.save()
        assert ligne.entreprise_id == A

    def test_autre_entreprise_refusee(self):
        ligne = Essai(libelle="x", entreprise_id=B)
        with contexte_entreprise(A), pytest.raises(ErreurIsolation):
            ligne.save()

    def test_meme_entreprise_en_texte_acceptee(self):
        ligne = Essai(libelle="x", entreprise_id=str(A))
        with contexte_entreprise(A):
            ligne.save()

    def test_hors_contexte_refuse(self):
        with pytest.raises(HorsContexteEntreprise):
            Essai(libelle="x").save()

    def test_plateforme_exige_une_entreprise_explicite(self):
        with portee_plateforme(motif="reprise"):
            with pytest.raises(ErreurIsolation):
                Essai(libelle="x").save()
            Essai(libelle="x", entreprise_id=A).save()


class TestInsertionEnMasse:
    """`bulk_create` ne passe pas par `save()` : l'entreprise doit être posée quand même."""

    @pytest.fixture(autouse=True)
    def sans_base(self):
        with mock.patch.object(models.QuerySet, "bulk_create", lambda self, objs, *a, **k: objs) as bc:
            yield bc

    def test_entreprise_remplie_depuis_le_contexte(self):
        lignes = [Essai(libelle="a"), Essai(libelle="b")]
        with contexte_entreprise(A):
            Essai.objects.bulk_create(lignes)
        assert {ligne.entreprise_id for ligne in lignes} == {A}

    def test_autre_entreprise_refusee(self):
        with contexte_entreprise(A), pytest.raises(ErreurIsolation):
            Essai.objects.bulk_create([Essai(libelle="a"), Essai(libelle="b", entreprise_id=B)])

    def test_hors_contexte_refuse(self):
        with pytest.raises(HorsContexteEntreprise):
            Essai.objects.bulk_create([Essai(libelle="a")])

    def test_plateforme_exige_une_entreprise_explicite(self):
        with portee_plateforme(motif="reprise"):
            with pytest.raises(ErreurIsolation):
                Essai.objects.bulk_create([Essai(libelle="a")])
            Essai.objects.bulk_create([Essai(libelle="a", entreprise_id=A)])


# --- L'authentification --------------------------------------------------------------------------
class TestAuthentification:
    def utilisateur(self, entreprise=..., pk=1):
        if entreprise is ...:
            return SimpleNamespace(pk=pk)  # lot 1 : pas encore de colonne
        return SimpleNamespace(pk=pk, entreprise_id=entreprise)

    def test_lot_1_sans_claim_ni_colonne_rien_ne_change(self):
        verifier_et_activer(self.utilisateur(), {"role_global": "DG"})
        assert entreprise_courante_id() is None

    def test_personnel_de_l_editeur_sans_entreprise(self):
        verifier_et_activer(self.utilisateur(entreprise=None), {})
        assert entreprise_courante_id() is None

    def test_claim_egal_active_l_entreprise(self):
        verifier_et_activer(self.utilisateur(entreprise=A), {"entreprise": str(A)})
        assert entreprise_courante_id() == A

    def test_claim_d_une_autre_entreprise_refuse(self):
        with pytest.raises(AuthenticationFailed):
            verifier_et_activer(self.utilisateur(entreprise=A), {"entreprise": str(B)})
        assert entreprise_courante_id() is None

    def test_compte_d_entreprise_sans_claim_refuse(self):
        with pytest.raises(AuthenticationFailed):
            verifier_et_activer(self.utilisateur(entreprise=A), {})

    def test_claim_pour_un_compte_sans_entreprise_refuse(self):
        with pytest.raises(AuthenticationFailed):
            verifier_et_activer(self.utilisateur(entreprise=None), {"entreprise": str(A)})


# --- Le middleware -------------------------------------------------------------------------------
def test_middleware_remet_a_zero_avant_et_apres():
    def vue(request):
        assert entreprise_courante_id() is None
        verifier_et_activer(SimpleNamespace(pk=1, entreprise_id=A), {"entreprise": str(A)})
        return "réponse"

    with contexte_entreprise(B):  # un fil réutilisé qui aurait gardé une entreprise
        assert ContexteEntrepriseMiddleware(vue)(object()) == "réponse"
        assert entreprise_courante_id() is None

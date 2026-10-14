from .auth import (
    ConnexionAdminView,
    DeconnexionAdminView,
    RenouvellementAdminView,
)
from .clients import (
    ActiverModuleClientPlateformeView,
    ChangerPlanClientPlateformeView,
    ClientsPlateformeListView,
    DesactiverModuleClientPlateformeView,
    FicheClientPlateformeView,
    ReactiverClientPlateformeView,
    SuspendreClientPlateformeView,
)
from .comptes import (
    AdminChangerMotDePasseMoiView,
    AdminPhotoMoiView,
    AdminProfilMoiView,
    ComptesAdministrateursListCreateView,
    ReactiverCompteAdministrateurView,
    SuspendreCompteAdministrateurView,
)
from .impersonation import (
    ActionsJournalPlateformeView,
    DeconnexionAssistanceView,
    DemarrerAssistanceView,
    JournalPlateformeListView,
    ListerUtilisateursEntrepriseView,
)
from .indicateurs import (
    EvolutionAbonnementsView,
    IndicateursPlateformeView,
    TendancesIndicateursView,
)
from .modules import (
    AdminModuleAffecterPermissionsView,
    AdminModuleDesactiverView,
    AdminModuleDetailUpdateDeleteView,
    AdminModuleListCreateView,
    AdminModuleReactiverView,
)
from .parametres import (
    AdminIdentiteView,
    AdminTarifsView,
    IdentitePublicView,
    TarifsPublicsView,
)
from .permissions import (
    AdminPermissionAffecterModulesView,
    AdminPermissionDetailUpdateDeleteView,
    AdminPermissionListCreateView,
)
from .reinitialisation import (
    DemandeReinitialisationAdminView,
    ReinitialisationAdminView,
    VerificationJetonAdminView,
)

__all__ = [
    "ActionsJournalPlateformeView",
    "ActiverModuleClientPlateformeView",
    "AdminChangerMotDePasseMoiView",
    "AdminIdentiteView",
    "AdminModuleAffecterPermissionsView",
    "AdminModuleDesactiverView",
    "AdminModuleDetailUpdateDeleteView",
    "AdminModuleListCreateView",
    "AdminModuleReactiverView",
    "AdminPermissionAffecterModulesView",
    "AdminPermissionDetailUpdateDeleteView",
    "AdminPermissionListCreateView",
    "AdminPhotoMoiView",
    "AdminProfilMoiView",
    "AdminTarifsView",
    "ChangerPlanClientPlateformeView",
    "ClientsPlateformeListView",
    "ComptesAdministrateursListCreateView",
    "ConnexionAdminView",
    "DeconnexionAdminView",
    "DeconnexionAssistanceView",
    "DemandeReinitialisationAdminView",
    "DemarrerAssistanceView",
    "DesactiverModuleClientPlateformeView",
    "EvolutionAbonnementsView",
    "FicheClientPlateformeView",
    "IdentitePublicView",
    "IndicateursPlateformeView",
    "JournalPlateformeListView",
    "ListerUtilisateursEntrepriseView",
    "ReactiverClientPlateformeView",
    "ReactiverCompteAdministrateurView",
    "ReinitialisationAdminView",
    "RenouvellementAdminView",
    "SuspendreClientPlateformeView",
    "SuspendreCompteAdministrateurView",
    "TarifsPublicsView",
    "TendancesIndicateursView",
    "VerificationJetonAdminView",
]

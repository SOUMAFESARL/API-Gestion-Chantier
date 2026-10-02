from .auth import (
    ConnexionAdminView,
    DeconnexionAdminView,
    RenouvellementAdminView,
)
from .clients import (
    ChangerPlanClientPlateformeView,
    ClientsPlateformeListView,
    FicheClientPlateformeView,
    ReactiverClientPlateformeView,
    SuspendreClientPlateformeView,
)
from .impersonation import (
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
from .reinitialisation import (
    DemandeReinitialisationAdminView,
    ReinitialisationAdminView,
    VerificationJetonAdminView,
)

from .comptes import (
    AdminChangerMotDePasseMoiView,
    AdminPhotoMoiView,
    AdminProfilMoiView,
    ComptesAdministrateursListCreateView,
    ReactiverCompteAdministrateurView,
    SuspendreCompteAdministrateurView,
)
from .modules import (
    AdminModuleAffecterPermissionsView,
    AdminModuleDesactiverView,
    AdminModuleDetailUpdateDeleteView,
    AdminModuleListCreateView,
    AdminModuleReactiverView,
)
from .permissions import (
    AdminPermissionAffecterModulesView,
    AdminPermissionDetailUpdateDeleteView,
    AdminPermissionListCreateView,
)

__all__ = [
    "AdminChangerMotDePasseMoiView",
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
    "ComptesAdministrateursListCreateView",
    "ReactiverCompteAdministrateurView",
    "SuspendreCompteAdministrateurView",
    "ChangerPlanClientPlateformeView",
    "ClientsPlateformeListView",
    "ConnexionAdminView",
    "DeconnexionAdminView",
    "DeconnexionAssistanceView",
    "DemandeReinitialisationAdminView",
    "DemarrerAssistanceView",
    "EvolutionAbonnementsView",
    "FicheClientPlateformeView",
    "IndicateursPlateformeView",
    "JournalPlateformeListView",
    "ListerUtilisateursEntrepriseView",
    "ReactiverClientPlateformeView",
    "ReinitialisationAdminView",
    "RenouvellementAdminView",
    "SuspendreClientPlateformeView",
    "TendancesIndicateursView",
    "VerificationJetonAdminView",
]

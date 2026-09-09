"""Référentiel des localités des pays où le produit s'inscrit.

Il sert **deux besoins** qui n'ont pas la même exigence :

* **proposer une liste de villes** au moment où l'on décrit une entreprise ou un
  chantier — il faut que le nom soit juste et que la ville soit reconnue par
  celui qui la choisit ;
* **résoudre des coordonnées GPS** pour l'interrogation météo — il faut que le
  point tombe sur la bonne agglomération, à quelques kilomètres près.

**La liste est fermée aux neuf pays de l'inscription.** Un pays absent de
`PAYS_AUTORISES` n'a pas de localités ici, et n'en aura pas tant qu'il ne peut
pas s'inscrire : deux listes de pays qui divergent, c'est une entreprise créée
dans un pays dont aucune ville ne s'affiche.

**Elle n'est pas exhaustive, et c'est assumé.** Chaque pays porte sa capitale,
ses chefs-lieux et ses villes secondaires — de quoi couvrir l'activité BTP
réelle. Ce qui manque se saisit à la main : l'écran garde une option « autre
localité », et c'est elle qui absorbe le village de brousse où se monte un
chantier.
"""

import unicodedata
from typing import TypedDict


class Localite(TypedDict):
    nom: str
    region: str
    # Appartient à l'agglomération principale du pays — les communes d'Abidjan,
    # de Dakar, de Conakry. Elles se choisissent séparément parce que c'est
    # ainsi qu'on situe un chantier là-bas : personne ne dit « Abidjan ».
    agglomeration: bool
    latitude: float
    longitude: float


# Le nom de l'agglomération, pour les trois pays qui en découpent une. Les six
# autres présentent une liste simple : y inventer un découpage qui ne se dit pas
# sur place ferait chercher « Douala » dans un groupe « Wouri ».
AGGLOMERATION_PRINCIPALE: dict[str, str] = {
    "CI": "Abidjan",
    "SN": "Dakar",
    "GN": "Conakry",
}

# La localité qui **représente** l'agglomération, quand on n'en dit que le nom.
# « Abidjan » n'est pas une commune : celui qui l'écrit désigne le centre, et le
# centre d'Abidjan est le Plateau. Prendre la première commune de la liste
# donnerait Cocody, ce qui est faux de trente kilomètres et surtout arbitraire.
CENTRE_AGGLOMERATION: dict[str, str] = {
    "CI": "Plateau",
    "SN": "Dakar",
    "GN": "Kaloum",
}


# Forme compacte : (nom, région, agglomération, latitude, longitude). Une ligne
# par localité — un dictionnaire par localité ferait 1 300 lignes pour la même
# information, et une liste qu'on ne relit pas est une liste qui se périme.
_LOCALITES_BRUTES: dict[str, tuple[tuple[str, str, bool, float, float], ...]] = {
    "CI": (
        ("Cocody", "District Autonome d'Abidjan", True, 5.3489, -3.9878),
        ("Yopougon", "District Autonome d'Abidjan", True, 5.3438, -4.0747),
        ("Plateau", "District Autonome d'Abidjan", True, 5.3261, -4.0197),
        ("Marcory", "District Autonome d'Abidjan", True, 5.3039, -3.9856),
        ("Treichville", "District Autonome d'Abidjan", True, 5.3094, -4.0089),
        ("Koumassi", "District Autonome d'Abidjan", True, 5.2981, -3.9531),
        ("Port-Bouët", "District Autonome d'Abidjan", True, 5.2571, -3.9481),
        ("Adjamé", "District Autonome d'Abidjan", True, 5.3589, -4.0267),
        ("Abobo", "District Autonome d'Abidjan", True, 5.4181, -4.0158),
        ("Attécoubé", "District Autonome d'Abidjan", True, 5.3333, -4.0417),
        ("Anyama", "District Autonome d'Abidjan", True, 5.4947, -4.0519),
        ("Bingerville", "District Autonome d'Abidjan", True, 5.3564, -3.8864),
        ("Songon", "District Autonome d'Abidjan", True, 5.3189, -4.2567),
        ("Yamoussoukro", "District Autonome de Yamoussoukro", False, 6.8276, -5.2893),
        ("Bouaké", "Gbêkê", False, 7.6906, -5.0300),
        ("San-Pédro", "San-Pédro", False, 4.7485, -6.6363),
        ("Daloa", "Haut-Sassandra", False, 6.8774, -6.4502),
        ("Korhogo", "Poro", False, 9.4580, -5.6296),
        ("Man", "Tonkpi", False, 7.4125, -7.5538),
        ("Gagnoa", "Gôh", False, 6.1319, -5.9506),
        ("Divo", "Lôh-Djiboua", False, 5.8374, -5.3572),
        ("Soubré", "Nawa", False, 5.7856, -6.6083),
        ("Abengourou", "Indénié-Djuablin", False, 6.7297, -3.4964),
        ("Grand-Bassam", "Sud-Comoé", False, 5.2100, -3.7388),
        ("Agboville", "Agnéby-Tiassa", False, 5.9280, -4.2133),
        ("Dabou", "Grands-Ponts", False, 5.3256, -4.3767),
        ("Odienné", "Kabadougou", False, 9.5051, -7.5643),
        ("Bondoukou", "Gontougo", False, 8.0402, -2.8000),
        ("Séguéla", "Worodougou", False, 7.9611, -6.6731),
        ("Ferkessédougou", "Tchologo", False, 9.6000, -5.2000),
        ("Boundiali", "Bagoué", False, 9.5217, -6.4869),
        ("Katiola", "Hambol", False, 8.1372, -5.1008),
        ("Daoukro", "Iffou", False, 7.0591, -3.9631),
        ("Adzopé", "La Mé", False, 6.1069, -3.8619),
        ("Aboisso", "Sud-Comoé", False, 5.4678, -3.2072),
        ("Bonoua", "Sud-Comoé", False, 5.2725, -3.5950),
        ("Sassandra", "Gbôklé", False, 4.9538, -6.0853),
        ("Tabou", "San-Pédro", False, 4.4230, -7.3528),
        ("Toumodi", "Bélier", False, 6.5574, -5.0177),
        ("Tiassalé", "Agnéby-Tiassa", False, 5.8983, -4.8228),
        ("Oumé", "Gôh", False, 6.3833, -5.4167),
        ("Issia", "Haut-Sassandra", False, 6.4922, -6.5856),
        ("Guiglo", "Cavally", False, 6.5436, -7.4936),
        ("Duékoué", "Guémon", False, 6.7419, -7.3492),
        ("Danané", "Tonkpi", False, 7.2597, -8.1550),
        ("Vavoua", "Haut-Sassandra", False, 7.3819, -6.4778),
        ("Zuénoula", "Marahoué", False, 7.4267, -6.0506),
        ("Sinématiali", "Poro", False, 9.5786, -5.3808),
        ("Tengréla", "Bagoué", False, 10.4811, -6.4069),
        ("Bouna", "Bounkani", False, 9.2692, -2.9997),
        ("Tanda", "Gontougo", False, 7.8033, -3.1683),
        ("Agnibilékrou", "Indénié-Djuablin", False, 7.1311, -3.2042),
        ("Bongouanou", "Moronou", False, 6.6517, -4.1986),
        ("Akoupé", "La Mé", False, 6.3842, -3.8967),
        ("Alépé", "La Mé", False, 5.4986, -3.6631),
        ("Jacqueville", "Grands-Ponts", False, 5.2053, -4.4144),
        ("Sikensi", "Agnéby-Tiassa", False, 5.6761, -4.5756),
    ),
    "SN": (
        ("Dakar", "Dakar", True, 14.6928, -17.4467),
        ("Pikine", "Dakar", True, 14.7549, -17.3900),
        ("Guédiawaye", "Dakar", True, 14.7767, -17.4056),
        ("Rufisque", "Dakar", True, 14.7167, -17.2667),
        ("Keur Massar", "Dakar", True, 14.7833, -17.3167),
        ("Bargny", "Dakar", True, 14.6947, -17.2264),
        ("Thiès", "Thiès", False, 14.7886, -16.9260),
        ("Mbour", "Thiès", False, 14.4198, -16.9646),
        ("Tivaouane", "Thiès", False, 14.9500, -16.8167),
        ("Kaolack", "Kaolack", False, 14.1500, -16.0667),
        ("Nioro du Rip", "Kaolack", False, 13.7500, -15.8000),
        ("Kaffrine", "Kaffrine", False, 14.1059, -15.5508),
        ("Diourbel", "Diourbel", False, 14.6522, -16.2314),
        ("Touba", "Diourbel", False, 14.8500, -15.8833),
        ("Mbacké", "Diourbel", False, 14.7833, -15.9167),
        ("Saint-Louis", "Saint-Louis", False, 16.0179, -16.4896),
        ("Richard-Toll", "Saint-Louis", False, 16.4625, -15.7009),
        ("Podor", "Saint-Louis", False, 16.6500, -14.9600),
        ("Louga", "Louga", False, 15.6144, -16.2244),
        ("Dahra", "Louga", False, 15.3428, -15.4783),
        ("Linguère", "Louga", False, 15.3833, -15.1167),
        ("Matam", "Matam", False, 15.6559, -13.2554),
        ("Tambacounda", "Tambacounda", False, 13.7708, -13.6673),
        ("Kédougou", "Kédougou", False, 12.5556, -12.1747),
        ("Kolda", "Kolda", False, 12.8833, -14.9500),
        ("Vélingara", "Kolda", False, 13.1500, -14.1167),
        ("Sédhiou", "Sédhiou", False, 12.7081, -15.5569),
        ("Ziguinchor", "Ziguinchor", False, 12.5833, -16.2719),
        ("Bignona", "Ziguinchor", False, 12.8103, -16.2264),
        ("Fatick", "Fatick", False, 14.3392, -16.4111),
        ("Foundiougne", "Fatick", False, 13.9167, -16.4667),
    ),
    "CM": (
        ("Douala", "Littoral", False, 4.0511, 9.7679),
        ("Edéa", "Littoral", False, 3.8000, 10.1333),
        ("Nkongsamba", "Littoral", False, 4.9547, 9.9404),
        ("Yaoundé", "Centre", False, 3.8480, 11.5021),
        ("Mbalmayo", "Centre", False, 3.5167, 11.5000),
        ("Obala", "Centre", False, 4.1667, 11.5333),
        ("Nanga-Eboko", "Centre", False, 4.6833, 12.3667),
        ("Garoua", "Nord", False, 9.3017, 13.3921),
        ("Guider", "Nord", False, 9.9333, 13.9500),
        ("Bamenda", "Nord-Ouest", False, 5.9597, 10.1494),
        ("Kumbo", "Nord-Ouest", False, 6.2000, 10.6667),
        ("Wum", "Nord-Ouest", False, 6.3833, 10.0667),
        ("Maroua", "Extrême-Nord", False, 10.5910, 14.3159),
        ("Kousséri", "Extrême-Nord", False, 12.0769, 15.0306),
        ("Yagoua", "Extrême-Nord", False, 10.3428, 15.2358),
        ("Bafoussam", "Ouest", False, 5.4781, 10.4176),
        ("Dschang", "Ouest", False, 5.4500, 10.0667),
        ("Foumban", "Ouest", False, 5.7167, 10.9000),
        ("Bafang", "Ouest", False, 5.1500, 10.1833),
        ("Mbouda", "Ouest", False, 5.6333, 10.2500),
        ("Ngaoundéré", "Adamaoua", False, 7.3167, 13.5833),
        ("Meiganga", "Adamaoua", False, 6.5167, 14.2917),
        ("Bertoua", "Est", False, 4.5776, 13.6846),
        ("Batouri", "Est", False, 4.4333, 14.3667),
        ("Ebolowa", "Sud", False, 2.9000, 11.1500),
        ("Kribi", "Sud", False, 2.9370, 9.9100),
        ("Sangmélima", "Sud", False, 2.9333, 11.9833),
        ("Buea", "Sud-Ouest", False, 4.1560, 9.2632),
        ("Limbe", "Sud-Ouest", False, 4.0186, 9.1949),
        ("Kumba", "Sud-Ouest", False, 4.6363, 9.4469),
        ("Tiko", "Sud-Ouest", False, 4.0750, 9.3600),
    ),
    "BF": (
        ("Ouagadougou", "Centre", False, 12.3714, -1.5197),
        ("Bobo-Dioulasso", "Hauts-Bassins", False, 11.1771, -4.2979),
        ("Orodara", "Hauts-Bassins", False, 10.9500, -4.9333),
        ("Koudougou", "Centre-Ouest", False, 12.2530, -2.3622),
        ("Réo", "Centre-Ouest", False, 12.3167, -2.4667),
        ("Léo", "Centre-Ouest", False, 11.1000, -2.1000),
        ("Banfora", "Cascades", False, 10.6333, -4.7667),
        ("Ouahigouya", "Nord", False, 13.5828, -2.4214),
        ("Yako", "Nord", False, 12.9667, -2.2667),
        ("Kaya", "Centre-Nord", False, 13.0919, -1.0847),
        ("Kongoussi", "Centre-Nord", False, 13.3167, -1.5333),
        ("Tenkodogo", "Centre-Est", False, 11.7800, -0.3697),
        ("Garango", "Centre-Est", False, 11.8000, -0.5500),
        ("Fada N'Gourma", "Est", False, 12.0616, 0.3583),
        ("Diapaga", "Est", False, 12.0708, 1.7889),
        ("Dédougou", "Boucle du Mouhoun", False, 12.4667, -3.4667),
        ("Nouna", "Boucle du Mouhoun", False, 12.7292, -3.8628),
        ("Boromo", "Boucle du Mouhoun", False, 11.7472, -2.9306),
        ("Tougan", "Boucle du Mouhoun", False, 13.0722, -3.0686),
        ("Solenzo", "Boucle du Mouhoun", False, 12.1833, -4.0833),
        ("Dori", "Sahel", False, 14.0354, -0.0345),
        ("Djibo", "Sahel", False, 14.1017, -1.6294),
        ("Gaoua", "Sud-Ouest", False, 10.3253, -3.1783),
        ("Ziniaré", "Plateau-Central", False, 12.5833, -1.3000),
        ("Manga", "Centre-Sud", False, 11.6642, -1.0733),
        ("Pô", "Centre-Sud", False, 11.1697, -1.1467),
    ),
    "ML": (
        ("Bamako", "District de Bamako", False, 12.6392, -8.0029),
        ("Kati", "Koulikoro", False, 12.7442, -8.0728),
        ("Koulikoro", "Koulikoro", False, 12.8628, -7.5599),
        ("Kolokani", "Koulikoro", False, 13.5728, -8.0333),
        ("Dioïla", "Koulikoro", False, 12.5000, -6.8000),
        ("Sikasso", "Sikasso", False, 11.3167, -5.6667),
        ("Koutiala", "Sikasso", False, 12.3917, -5.4642),
        ("Bougouni", "Sikasso", False, 11.4167, -7.4833),
        ("Yanfolila", "Sikasso", False, 11.1783, -8.1478),
        ("Ségou", "Ségou", False, 13.4317, -6.2158),
        ("San", "Ségou", False, 13.3033, -4.8961),
        ("Niono", "Ségou", False, 14.2531, -5.9931),
        ("Markala", "Ségou", False, 13.6764, -6.0664),
        ("Bla", "Ségou", False, 12.9500, -5.7667),
        ("Mopti", "Mopti", False, 14.4843, -4.1829),
        ("Sévaré", "Mopti", False, 14.5333, -4.1000),
        ("Djenné", "Mopti", False, 13.9061, -4.5550),
        ("Bandiagara", "Mopti", False, 14.3500, -3.6100),
        ("Douentza", "Mopti", False, 15.0000, -2.9500),
        ("Kayes", "Kayes", False, 14.4469, -11.4444),
        ("Kita", "Kayes", False, 13.0350, -9.4894),
        ("Nioro du Sahel", "Kayes", False, 15.2300, -9.5900),
        ("Bafoulabé", "Kayes", False, 13.8069, -10.8322),
        ("Gao", "Gao", False, 16.2667, -0.0500),
        ("Ansongo", "Gao", False, 15.6600, 0.5000),
        ("Tombouctou", "Tombouctou", False, 16.7735, -3.0074),
        ("Kidal", "Kidal", False, 18.4411, 1.4078),
    ),
    "TG": (
        ("Lomé", "Maritime", False, 6.1319, 1.2228),
        ("Tsévié", "Maritime", False, 6.4264, 1.2136),
        ("Aného", "Maritime", False, 6.2281, 1.5919),
        ("Vogan", "Maritime", False, 6.3333, 1.5333),
        ("Tabligbo", "Maritime", False, 6.5833, 1.5000),
        ("Sokodé", "Centrale", False, 8.9833, 1.1333),
        ("Tchamba", "Centrale", False, 9.0333, 1.4167),
        ("Sotouboua", "Centrale", False, 8.5667, 0.9833),
        ("Blitta", "Centrale", False, 8.3167, 0.9833),
        ("Kara", "Kara", False, 9.5511, 1.1861),
        ("Bassar", "Kara", False, 9.2500, 0.7833),
        ("Kandé", "Kara", False, 9.9500, 1.0500),
        ("Niamtougou", "Kara", False, 9.7667, 1.1000),
        ("Kpalimé", "Plateaux", False, 6.9000, 0.6333),
        ("Atakpamé", "Plateaux", False, 7.5333, 1.1333),
        ("Notsé", "Plateaux", False, 6.9500, 1.1667),
        ("Badou", "Plateaux", False, 7.5833, 0.6000),
        ("Amlamé", "Plateaux", False, 7.4667, 0.9000),
        ("Dapaong", "Savanes", False, 10.8622, 0.2075),
        ("Mango", "Savanes", False, 10.3600, 0.4700),
    ),
    "BJ": (
        ("Cotonou", "Littoral", False, 6.3667, 2.4333),
        ("Porto-Novo", "Ouémé", False, 6.4969, 2.6289),
        ("Abomey-Calavi", "Atlantique", False, 6.4486, 2.3556),
        ("Ouidah", "Atlantique", False, 6.3667, 2.0833),
        ("Allada", "Atlantique", False, 6.6653, 2.1511),
        ("Parakou", "Borgou", False, 9.3372, 2.6303),
        ("Nikki", "Borgou", False, 9.9401, 3.2108),
        ("Bembèrèkè", "Borgou", False, 10.2283, 2.6664),
        ("Djougou", "Donga", False, 9.7000, 1.6667),
        ("Bohicon", "Zou", False, 7.1783, 2.0667),
        ("Abomey", "Zou", False, 7.1858, 1.9914),
        ("Natitingou", "Atacora", False, 10.3042, 1.3794),
        ("Tanguiéta", "Atacora", False, 10.6200, 1.2650),
        ("Kandi", "Alibori", False, 11.1342, 2.9386),
        ("Malanville", "Alibori", False, 11.8681, 3.3894),
        ("Banikoara", "Alibori", False, 11.2986, 2.4386),
        ("Lokossa", "Mono", False, 6.6389, 1.7167),
        ("Comè", "Mono", False, 6.4000, 1.8833),
        ("Grand-Popo", "Mono", False, 6.2833, 1.8167),
        ("Savalou", "Collines", False, 7.9281, 1.9756),
        ("Dassa-Zoumé", "Collines", False, 7.7500, 2.1833),
        ("Pobè", "Plateau", False, 6.9800, 2.6650),
        ("Kétou", "Plateau", False, 7.3600, 2.6000),
        ("Sakété", "Plateau", False, 6.7364, 2.6586),
        ("Aplahoué", "Couffo", False, 6.9333, 1.6833),
    ),
    "GN": (
        ("Kaloum", "Conakry", True, 9.5092, -13.7122),
        ("Dixinn", "Conakry", True, 9.5500, -13.6833),
        ("Matam", "Conakry", True, 9.5333, -13.6667),
        ("Ratoma", "Conakry", True, 9.5833, -13.6333),
        ("Matoto", "Conakry", True, 9.5667, -13.6000),
        ("Nzérékoré", "Nzérékoré", False, 7.7561, -8.8179),
        ("Macenta", "Nzérékoré", False, 8.5500, -9.4667),
        ("Guéckédou", "Nzérékoré", False, 8.5667, -10.1333),
        ("Beyla", "Nzérékoré", False, 8.6833, -8.6500),
        ("Lola", "Nzérékoré", False, 7.8000, -8.5333),
        ("Kankan", "Kankan", False, 10.3854, -9.3057),
        ("Siguiri", "Kankan", False, 11.4147, -9.1667),
        ("Kérouané", "Kankan", False, 9.2667, -9.0167),
        ("Mandiana", "Kankan", False, 10.6333, -8.6833),
        ("Kindia", "Kindia", False, 10.0569, -12.8658),
        ("Coyah", "Kindia", False, 9.7000, -13.3833),
        ("Dubréka", "Kindia", False, 9.7833, -13.5167),
        ("Forécariah", "Kindia", False, 9.4333, -13.1000),
        ("Télimélé", "Kindia", False, 10.9000, -13.0333),
        ("Labé", "Labé", False, 11.3167, -12.2833),
        ("Tougué", "Labé", False, 11.4333, -11.6667),
        ("Boké", "Boké", False, 10.9333, -14.3000),
        ("Kamsar", "Boké", False, 10.6500, -14.6167),
        ("Fria", "Boké", False, 10.3667, -13.5833),
        ("Koundara", "Boké", False, 12.4833, -13.3000),
        ("Mamou", "Mamou", False, 10.3756, -12.0914),
        ("Dalaba", "Mamou", False, 10.6900, -12.2500),
        ("Pita", "Mamou", False, 11.0833, -12.4000),
        ("Faranah", "Faranah", False, 10.0400, -10.7433),
        ("Kissidougou", "Faranah", False, 9.1850, -10.1000),
        ("Dabola", "Faranah", False, 10.7500, -11.1167),
    ),
    "GA": (
        ("Libreville", "Estuaire", False, 0.4162, 9.4673),
        ("Owendo", "Estuaire", False, 0.2833, 9.5000),
        ("Akanda", "Estuaire", False, 0.5333, 9.4333),
        ("Ntoum", "Estuaire", False, 0.3833, 9.7667),
        ("Cocobeach", "Estuaire", False, 1.0000, 9.5833),
        ("Port-Gentil", "Ogooué-Maritime", False, -0.7193, 8.7815),
        ("Gamba", "Ogooué-Maritime", False, -2.6500, 10.0000),
        ("Franceville", "Haut-Ogooué", False, -1.6333, 13.5833),
        ("Moanda", "Haut-Ogooué", False, -1.5333, 13.2000),
        ("Okondja", "Haut-Ogooué", False, -0.6833, 13.6833),
        ("Oyem", "Woleu-Ntem", False, 1.5993, 11.5793),
        ("Bitam", "Woleu-Ntem", False, 2.0757, 11.4930),
        ("Mitzic", "Woleu-Ntem", False, 0.7833, 11.5500),
        ("Mouila", "Ngounié", False, -1.8681, 11.0553),
        ("Fougamou", "Ngounié", False, -1.2167, 10.5833),
        ("Lambaréné", "Moyen-Ogooué", False, -0.7001, 10.2300),
        ("Ndjolé", "Moyen-Ogooué", False, -0.1833, 10.7667),
        ("Tchibanga", "Nyanga", False, -2.9333, 10.9833),
        ("Mayumba", "Nyanga", False, -3.4167, 10.6500),
        ("Koulamoutou", "Ogooué-Lolo", False, -1.1367, 12.4667),
        ("Lastoursville", "Ogooué-Lolo", False, -0.8167, 12.7167),
        ("Makokou", "Ogooué-Ivindo", False, 0.5738, 12.8642),
        ("Booué", "Ogooué-Ivindo", False, -0.0928, 11.9364),
    ),
}


LOCALITES: dict[str, list[Localite]] = {
    pays: [
        {
            "nom": nom,
            "region": region,
            "agglomeration": agglomeration,
            "latitude": latitude,
            "longitude": longitude,
        }
        for nom, region, agglomeration, latitude, longitude in lignes
    ]
    for pays, lignes in _LOCALITES_BRUTES.items()
}


def normaliser_chaine(texte: str) -> str:
    """Minuscule, sans accent, sans trait d'union ni apostrophe — pour comparer.

    Celui qui saisit écrit « bouake », « Bouaké » ou « BOUAKE » ; il écrit aussi
    « san pedro » pour San-Pédro et « Fada Ngourma » pour Fada N'Gourma. Ce sont
    chaque fois la même ville, et l'API météo n'a qu'un point de coordonnées.
    """
    if not texte:
        return ""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    sans_ponctuation = sans_accent.lower().replace("-", " ").replace("'", " ")
    return " ".join(sans_ponctuation.split())


def pays_couvert(pays: str) -> bool:
    """Le pays a-t-il des localités ici."""
    return bool(pays) and pays.strip().upper() in LOCALITES


def lister_villes(pays: str) -> list[Localite]:
    """Les localités d'un pays, par ordre alphabétique. Liste vide si inconnu.

    **Vide, et non une erreur** : l'écran qui appelle affiche alors son option
    de saisie libre, ce qui est exactement le comportement voulu pour un pays
    qu'on n'a pas encore documenté.
    """
    return sorted(LOCALITES.get((pays or "").strip().upper(), []), key=lambda x: x["nom"])


def nom_agglomeration(pays: str) -> str:
    """Le nom de l'agglomération principale, ou une chaîne vide."""
    return AGGLOMERATION_PRINCIPALE.get((pays or "").strip().upper(), "")


def resoudre_coordonnees(nom: str, pays: str = "CI") -> tuple[str, float, float] | None:
    """Nom canonique et coordonnées GPS d'une localité, dans le pays donné.

    C'est une **résolution de données**, pas une décision de produit : elle
    répond pour les neuf pays. Savoir si la météo s'affiche dans tel pays est
    une question de service, et elle se tranche dans `services/meteo.py`.

    Trois passes, de la plus stricte à la plus tolérante : nom exact normalisé,
    nom de l'agglomération seule (« Abidjan », « Dakar »), puis sous-chaîne —
    c'est elle qui rattrape les valeurs héritées de la forme « Abidjan - Cocody ».
    """
    code = (pays or "").strip().upper()
    localites = LOCALITES.get(code)
    if not localites:
        return None

    def centre() -> tuple[str, float, float] | None:
        attendu = normaliser_chaine(CENTRE_AGGLOMERATION.get(code, ""))
        if not attendu:
            return None
        for loc in localites:
            if normaliser_chaine(loc["nom"]) == attendu:
                return (loc["nom"], loc["latitude"], loc["longitude"])
        return None

    if not nom or not nom.strip():
        # Sans ville, on prend le cœur de l'agglomération principale, ou à
        # défaut la première localité du pays — sa capitale, par construction
        # de la liste.
        defaut = centre()
        if defaut:
            return defaut
        premiere = localites[0]
        return (premiere["nom"], premiere["latitude"], premiere["longitude"])

    saisie = normaliser_chaine(nom)

    for loc in localites:
        if normaliser_chaine(loc["nom"]) == saisie:
            return (loc["nom"], loc["latitude"], loc["longitude"])

    # « Abidjan » n'est pas une commune : c'est le nom du district. Celui qui
    # l'écrit veut le centre, et le centre d'Abidjan est le Plateau.
    if saisie == normaliser_chaine(nom_agglomeration(code)):
        agglo = centre()
        if agglo:
            return agglo

    for loc in localites:
        norme = normaliser_chaine(loc["nom"])
        if saisie in norme or norme in saisie:
            return (loc["nom"], loc["latitude"], loc["longitude"])

    # Dernière passe, sans aucune séparation : « Fada Ngourma » et
    # « Fada N'Gourma » ne se rejoignent qu'ici, l'apostrophe étant devenue une
    # espace d'un côté et rien de l'autre.
    colle = saisie.replace(" ", "")
    for loc in localites:
        if normaliser_chaine(loc["nom"]).replace(" ", "") == colle:
            return (loc["nom"], loc["latitude"], loc["longitude"])

    return None

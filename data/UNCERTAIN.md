# Pistes ACP Renewables non confirmées (Phase 1)

> Parcs ou portefeuilles pour lesquels une mention d'investissement ACP/Allianz a été identifiée
> dans la presse publique mais où coordonnées, capacité, ou périmètre asset-level n'ont pas pu être
> verrouillés à un niveau suffisant pour valider une entrée dans `parks_index.yaml`.
>
> Phase 2+ : à reprendre si les besoins analytiques le justifient (ex. obtenir les sites individuels
> des portefeuilles BESS allemands, raffiner les coordonnées des sites Spain ACP).

## Période 2010-2017

- **Brindisi Solar (entrée `brindisi` dans `parks_index.yaml`)** — IT, 2010. Mentionné par Allianz comme "premier investissement solaire d'Allianz Specialised Investments en 2010" mais aucune source publique ne confirme la capacité (MWp), l'opérateur, ni les coordonnées exactes du site. Le seul deal italien proche dans le temps publiquement documenté est l'achat à BP Solar Italy de six centrales de 1 MWp en mai 2010 (6 MW total, sites non nommés). Le parc Torre Santa Susanna 7,56 MW (Brindisi province, COD avr 2011) liste un "investisseur non disclosé" sans confirmer Allianz. Conséquence : `capacity_mwp: null` + `excluded_from_sweep: true` dans le YAML — le parc reste sur le globe pour transparence du périmètre 2010 mais est exclu du sweep PVGIS tant qu'une source primaire ne confirme pas la capacité.
  - Sources : <https://renewablesnow.com/news/allianz-snaps-6-mw-pv-assets-from-bp-solar-67079/>, <https://www.power-technology.com/projects/torre-santa-susanna-solar-park/>, <https://www.allianz.com/content/dam/onemarketing/azcom/Allianz_com/migration/media/press/document/other/factsheet_asi_21012011_en.pdf>

- **ImWind Austrian Portfolio (Scharndorf III, Zistersdorf Ost, Ladendorf, Großkrut-Hauskirchen-Wilfersdorf)** — AT, ~2015. 4 parcs éoliens, 21 turbines, 65 MW total, tous dans un rayon de 70 km de Vienne ; premier deal autrichien ACP (closing fév 2015). Coords disponibles pour Scharndorf I/II/West mais pas confirmées pour Scharndorf III ; les 3 autres sites non géoréférencés. À introduire en portfolio entry similaire à `france-2013-portfolio` une fois sites individuels géocodés.
  - Sources : <https://mergr.com/transaction/allianz-capital-partners-acquires-imwind-group-four-austrian-wind-projects>, <https://renewablesnow.com/news/allianz-to-acquire-65-mw-of-wind-capacity-in-austria-483237/>

- **Maevaara Phase 2 (33 MW extension)** — SE, 2016. Extension du parc Maevaara avec coords plausibles 66.9407, 23.3065. Actuellement consolidé dans l'entrée principale `maevaara` (capacity 105 MW = phase 1 + phase 2). Pourrait être éclaté en entrée distincte si granularité plus fine souhaitée.
  - Source : <https://renewablesnow.com/news/allianz-buys-all-of-105-mw-swedish-wind-farm-461676/>

- **Jouttikallio Part 2 (~21 MW extension)** — FI, ~2017. thewindpower.net liste un second jeu de turbines Vestas (21 MW) aux coords 62.9236, 23.0581 adjacent au premier ; possession ACP de Part 2 non confirmée explicitement dans la presse publique.
  - Source : <https://www.thewindpower.net/windfarm_en_24972_jouttikallio.php>

- **Allianz / EDF Kelly Creek Wind** — US, jan 2017. ACP a participé à un investissement tax-equity sur un parc EDF dans l'Illinois ; capacité et localisation exactes à confirmer si on veut l'ajouter en bord de fenêtre 2017.
  - Source : <https://www.allianzcapitalpartners.com/media/news/01717-allianz-invests-edf-wind-farm-illinois/>

## Période 2018-2022

- **Allianz Spain solar 2019-2022** — Plusieurs mentions d'un "Iberian portfolio" ACP mais aucun actif individuel publiquement disclosé sur 2019-2022 (le deal Grenergy 300 MW a closé oct 2023, hors fenêtre).
  - Source : <https://solarquarter.com/2023/10/20/grenergys-solar-deal-allianz-acquires-300mw-solar-power-in-spain-for-over-e270-million/>

- **Beacon Wind (US offshore)** — Détenu par Equinor + bp 2020-2024 ; aucune participation Allianz trouvée dans les sources publiques. Skip pour l'atlas.

- **Hornsea / Triton Knoll / East Anglia / Race Bank (UK offshore)** — Aucune participation ACP confirmée dans la presse 2018-2022 ; le seul actif offshore UK ACP reste Galloper. Skip.

## Période 2023-2026

- **GESI Battery Storage Platform** — DE, deal avr 2026, ~2.6 GW pre-development. Trois sites en Bavière + Basse-Saxe, coords asset-level non publiées, COD pas avant 2029. À reprendre quand Kyon / GESI publient la liste des sites.
  - Source : <https://www.allianzgi.com/en/press-centre/media/press-releases/20260423-allianzgi-acquires-51-percent-stake-in-gesi>

- **Amprion German grid stake** — DE, mars 2026. Réseau de transmission, hors scope renewables generation. Volontairement exclu de l'atlas.
  - Source : <https://www.allianzcapitalpartners.com/en/media/news/20260326-allianzgi-buys-stake-in-german-grid-amprion>

- **Italie / UK 2023-2025 deals** — Aucune press release ACP publique identifiée 2023-2026 pour de nouveaux assets en Italie ou au UK. L'exposition existante semble pre-2023.

## Méthodologie de cartographie Phase 1

- **3 sous-agents** ont scrapé les press releases ACP / Allianz / opérateurs partenaires
  par fenêtre temporelle (2010-2017, 2018-2022, 2023-2026) en avril 2026.
- Critère d'inclusion dans `parks_index.yaml` : coordonnées lat/lon d'un actif réel
  (vs. centroid pays), URL press release canonique, et stake ACP attesté publiquement.
- Toute ambiguïté → atterrit dans ce fichier plutôt que de polluer l'index master.
- Le périmètre 23/150+ assumé reflète strictement la donnée publique disponible — le reste
  du portefeuille ACP (Macquarie Infrastructure Fund V, Brookfield Infrastructure, etc.)
  ne nomme pas les assets sous-jacents.

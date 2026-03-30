VERY_QUICK = [
    'mickey', 'quadfor2', 'sparse5', 'lanconelli', 'test', 'hunecke',
    'solotarev', 'chandra4', 'conform1', 'lorentz', 'quadgrid', 'hairer1',
    'hemmecke', 'liu', 'puma', 's9_1', 'boon', 'heart', 'reif', 'caprasse',
    'ku10', 'chandra5', 'issac97', 'comb3000', 'comb3000s', 'morgenstern',
    'hcyclic5', 'rose', 'redcyc5', 'cyclic5', 'extcyc4', 'redeco7',
    'uteshev_bikker', 'chemequ', 'geneig', 'chandra6', 'lichtblau',
    'vermeer', 'chemequs', 'f633', 'camera1s', 'tangents', 'matrix',
    'eco7', 'cassou'
]

QUICK = [
    'rabmo', 'butcher', 'redeco8', 'des18_3', 'cohn2', 'dessin1',
    'des22_24', 'reimer4', 'hcyclic6', 'kinema', 'dessin2', 'noon5',
    'katsura6', 'speer', 'redcyc6'
]

MEDIUM = [
    'cyclic6', 'butcher8', 'eco8', 'redeco9', 'kin1', 'd1',
    'benchmark_D1', 'extcyc5', 'cpdm5', 'katsura7', 'reimer5',
    'rbpl24', 'fabrice24'
]

LONG = [
    'jcf26', 'filter9', 'hietarinta1', 'hf744', 'noon6',
    'benchmark_i1', 'rbpl', 'i1', 'cohn3', 'assur44', 'f744',
    'eco9', 'kotsireas', 'redeco10', 'chemkin', 'katsura8'
]

TOO_LONG = [
    'reimer6', 'hairer2', 'redeco11', 'pinchon1', 'el44',
    'eco10', 'ilias_k_3', 'hairer3', 'dl', 'katsura9', 'noon7'
]


CATEGORY_MAP = {
    "very_quick": VERY_QUICK,
    "quick": QUICK,
    "medium": MEDIUM,
	"long": LONG,
    "too_long": TOO_LONG,
}

SUMMARY_COLUMNS = [
    "Имя теста",
    "Время (с)",
    "Размерность",
    "crit1",
    "crit2",
    "Средняя память (MB)",
    "Максимальная память (MB)",
    "Кол. уравнений",
    "Кол. переменных",
    "Память в секунду (MB/s)",
    "Сумма критериев",
]

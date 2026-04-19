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

DEFAULT_TIMEOUT_SEC = 7200

BENCHMARK_CONFIGS = {
    "B00": {
        "cpu": "7",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C0.1": {
        "cpu": "0.1",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C0.25": {
        "cpu": "0.25",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C0.5": {
        "cpu": "0.5",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C0.75": {
        "cpu": "0.75",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C01": {
        "cpu": "1",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "C04": {
        "cpu": "4",
        "ram": "4g",
        "swap_budget": "0g",
    },
    "R0.5": {
        "cpu": "7",
        "ram": "0.5g",
        "swap_budget": "0g",
    },
    "R01": {
        "cpu": "7",
        "ram": "1g",
        "swap_budget": "0g",
    },
    "S02": {
        "cpu": "7",
        "ram": "0.5g",
        "swap_budget": "2g",
    },
    "S04": {
        "cpu": "7",
        "ram": "0.5g",
        "swap_budget": "4g",
    },
}

RAW_SUMMARY_COLUMNS = [
    "run_id",
    "repeat_index",
    "config_name",
    "cpu_limit",
    "memory_limit_mb",
    "memswap_limit_mb",
    "swap_budget_mb",
    "timeout_sec",
    "test_name",
    "category",
    "status",
    "duration_sec",
    "rss_avg_mb",
    "rss_peak_mb",
    "user_cpu_time_sec",
    "system_cpu_time_sec",
    "cpu_time_total_sec",
    "major_page_faults",
    "minor_page_faults",
    "voluntary_context_switches",
    "involuntary_context_switches",
    "block_input_ops",
    "block_output_ops",
    "crit1",
    "crit2",
    "crit_sum",
    "dimension",
    "equation_count",
    "variable_count",
]

AGGREGATED_COLUMNS = [
    "config_name",
    "test_name",
    "category",
    "runs_count",
    "ok_runs",
    "timeout_runs",
    "error_runs",
    "completion_rate",
    "duration_mean_sec",
    "duration_median_sec",
    "duration_std_sec",
    "duration_min_sec",
    "duration_max_sec",
    "rss_peak_mean_mb",
    "rss_peak_max_mb",
    "major_page_faults_mean",
    "minor_page_faults_mean",
    "crit_sum_mean",
]

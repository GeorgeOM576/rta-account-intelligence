"""Representative workload and a guard against full Cartesian fuzzy scoring."""
import time
import polars as pl
from rta.models import Mapping
from rta.matching import Matcher


def test_250_master_53000_source():
    source = pl.DataFrame({'Company': [f'Synthetic Account {i:05}' for i in range(53000)],
                           'Value': ['Enterprise'] * 53000})
    names = [f'Synthetic Account {i:05}' for i in range(200)] + [f'Synthetik Account {i:05}' for i in range(200, 250)]
    master = pl.DataFrame({'Account': names, 'Segment': ['Enterprise'] * 250})
    start = time.perf_counter()
    matcher = Matcher(source, Mapping('Account', 'Company', 'Segment', 'Value'))
    results = matcher.run(master)
    elapsed = time.perf_counter() - start
    print(f'\n250 x 53,000 workload: {elapsed:.2f}s')
    assert len(results) == 250 and sum(r.match_status == 'Exact' for r in results) == 200
    assert all(len(r.candidates) == 3 for r in results)
    assert all(not r.final for r in results[200:])

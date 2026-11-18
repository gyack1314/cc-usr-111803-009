"""修订说明与新版报告分批到达时，事实、预测、修订必须分开呈现。"""
import tempfile
import unittest
from pathlib import Path
from capture_service.ledger import connect, raw_receipt
from capture_service.collection import collect, coverage
from capture_service.view import overview
from capture_service.archive import release_verified, release, get

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = '111803-009'
REPORT_URL = 'https://local-source-009.example.test/records/market_report-A'
AMENDMENT_URL = 'https://local-source-009.example.test/records/report_amendment-A'


class AmendmentLifecycle(unittest.TestCase):
    def _load(self, connection, *manifests):
        for name in manifests:
            collect(connection, COLLECTION, ROOT / 'data' / name)

    def test_amendment_first_blocks_old_report_as_current_view(self):
        with tempfile.TemporaryDirectory() as directory:
            c = connect(Path(directory) / 'state.sqlite3')
            self._load(c, 'normal.json', 'event-complete.json')
            view = overview(c, COLLECTION)
            study = view['studies'][0]
            # 修订说明先到、新版报告未取得：旧报告不是现行观点，也不能发布为已核实。
            self.assertIsNone(study['current_prediction'])
            self.assertEqual([r['status'] for r in study['report_versions']], ['revision_pending'])
            self.assertEqual([a['status'] for a in study['amendments']], ['pending'])
            self.assertFalse(view['publishable'])
            self.assertTrue(any(p['relation'] == 'amendment_awaits_report'
                                for p in view['pending_relations']))
            self.assertIn(AMENDMENT_URL, coverage(c, COLLECTION)['unverified_required'])
            with self.assertRaises(ValueError):
                release_verified(c, COLLECTION)
            # 原话仍可查看，读者不会丢失机构原文。
            digest = study['report_versions'][0]['source_sha256']
            receipt = raw_receipt(c, COLLECTION, digest)
            self.assertIn('2026-W47', receipt['raw'].decode('utf-8'))
            self.assertEqual(receipt['source_url'], REPORT_URL)
            c.close()

    def test_new_report_arrives_but_spot_keeps_its_observed_week(self):
        with tempfile.TemporaryDirectory() as directory:
            c = connect(Path(directory) / 'state.sqlite3')
            self._load(c, 'normal.json', 'event-complete.json', 'revised.json')
            view = overview(c, COLLECTION)
            study = view['studies'][0]
            # 现行观点切换到 v2/W48；v1/W47 仅作历史版本保留。
            self.assertEqual(study['current_prediction']['report_version'], 'v2')
            self.assertEqual(study['current_prediction']['prediction_week'], '2026-W48')
            self.assertEqual([(r['report_version'], r['status']) for r in study['report_versions']],
                             [('v1', 'superseded'), ('v2', 'current')])
            self.assertEqual(study['amendments'][0]['status'], 'fulfilled')
            # W46 现货仍是 W46 事实，不被标成 W48 实绩；W48 保持待核关系。
            self.assertEqual([f['observed_week'] for f in view['spot_facts']], ['2026-W46'])
            self.assertTrue(all('不构成任何预测周实绩' in f['evidence_scope']
                                for f in view['spot_facts']))
            pending = view['pending_relations']
            gap = next(p for p in pending if p['relation'] == 'prediction_without_observation')
            self.assertEqual(gap['prediction_week'], '2026-W48')
            for pair in view['matched_pairs']:
                self.assertEqual(pair['observed_week'], '2026-W46')
                self.assertNotEqual(pair['observed_week'], pair['prediction_week'])
            self.assertEqual(coverage(c, COLLECTION)['unverified_required'], [])
            revision = release_verified(c, COLLECTION)
            self.assertTrue(get(c, COLLECTION, revision)['publishable'])
            c.close()

    def test_historical_release_keeps_then_current_versions_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            c = connect(Path(directory) / 'state.sqlite3')
            collect(c, COLLECTION, ROOT / 'data' / 'normal.json')
            historical = release_verified(c, COLLECTION)
            frozen = get(c, COLLECTION, historical)
            # 历史周报保留当时引用的报告版本与现货依据。
            frozen_study = frozen['studies'][0]
            self.assertEqual(frozen_study['current_prediction']['report_version'], 'v1')
            self.assertEqual(frozen_study['current_prediction']['prediction_week'], '2026-W47')
            self.assertEqual(frozen_study['report_versions'][0]['spot_citations'][0]['observed_week'],
                             '2026-W46')
            self._load(c, 'event-complete.json', 'revised.json')
            current = overview(c, COLLECTION)
            self.assertEqual(current['studies'][0]['current_prediction']['report_version'], 'v2')
            # 已发布视图不被后续资料改写。
            self.assertEqual(get(c, COLLECTION, historical), frozen)
            c.close()

    def test_amendment_without_any_report_shows_concrete_pending_relation(self):
        with tempfile.TemporaryDirectory() as directory:
            c = connect(Path(directory) / 'state.sqlite3')
            # 目录先登记三类来源，只取得修订说明原文。
            self._load(c, 'event-pending.json', 'event-complete.json')
            view = overview(c, COLLECTION)
            self.assertFalse(view['publishable'])
            relations = {p['relation'] for p in view['pending_relations']}
            self.assertIn('amendment_awaits_report', relations)
            self.assertIn('spot_reference_missing', relations)
            # 资料没有被隐藏：修订原话与待核关系同时可见。
            self.assertEqual(view['received_versions'], 1)
            self.assertEqual(view['studies'][0]['amendments'][0]['status'], 'unverifiable')
            self.assertIn('无法核对修订对象', view['studies'][0]['amendments'][0]['detail'])
            with self.assertRaises(ValueError):
                release_verified(c, COLLECTION)
            c.close()


if __name__ == '__main__':
    unittest.main()

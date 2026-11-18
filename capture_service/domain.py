"""解析来源身份，并把资料区分为现货事实、未来预测与后续修订。

report_id 只是来源声明的关联线索，字段相等不证明跨来源归属；现货表只能
支持其自身观察周的事实，报告预测在观察周到来前不能被标为已证实；修订说明
与新版报告按 replaces_revision 分开核对，修订先到而新版未到时保持待核。
"""
import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / 'docs' / 'source-contract.json').read_text(encoding='utf-8'))
REPORT_ROLE, SPOT_ROLE, AMENDMENT_ROLE = CONTRACT['roles']


def decode(raw, receipt):
    doc = json.loads(raw.decode('utf-8'))
    if not all(k in doc for k in ('kind', 'id', 'revision')):
        raise ValueError('资料身份缺失')
    kind = doc['kind']
    if kind not in CONTRACT['roles']:
        raise ValueError('未知来源类型')
    if any(k not in doc for k in CONTRACT['required_fields'][kind]):
        raise ValueError('来源业务字段缺失')
    return [{'type': kind, 'id': doc['id'], 'version': doc['revision'],
             'payload': {k: v for k, v in doc.items() if k not in ('kind', 'id', 'revision')}}]


def _by_version(rows):
    return sorted(rows, key=lambda r: r['version'])


def _fact_view(spot):
    p = spot['payload']
    return {'spot_id': spot['id'], 'spot_version': spot['version'], 'source_sha256': spot['source'],
            'report_id': p['report_id'], 'observed_week': p['observed_week'],
            'price_cny_kg': p['price_cny_kg'],
            'evidence_scope': f"现货事实仅支持观察周 {p['observed_week']} 的价格，不构成任何预测周实绩"}


def assess(rows):
    """按业务事实核对候选资料，输出事实、预测、修订与具体待核关系。"""
    reports = _by_version([r for r in rows if r['type'] == REPORT_ROLE])
    spots = _by_version([r for r in rows if r['type'] == SPOT_ROLE])
    amendments = _by_version([r for r in rows if r['type'] == AMENDMENT_ROLE])

    # 可由现货表支持的事实：每条现货只陈述其自身观察周。
    spot_facts = [_fact_view(s) for s in spots]

    study_ids = sorted({r['payload']['report_id'] for r in reports}
                       | {s['payload']['report_id'] for s in spots}
                       | {a['payload']['report_id'] for a in amendments})

    studies = []
    all_pending = []
    verified_digests = set()
    blocking = []

    for report_id in study_ids:
        study_reports = _by_version([r for r in reports if r['payload']['report_id'] == report_id])
        study_spots = _by_version([s for s in spots if s['payload']['report_id'] == report_id])
        study_amendments = _by_version([a for a in amendments if a['payload']['report_id'] == report_id])

        # 修订与实际收到的新版报告分别核对。
        amendment_views = []
        for a in study_amendments:
            ap = a['payload']
            target = next((r for r in study_reports if r['version'] == ap['replaces_revision']), None)
            successor = next((r for r in study_reports if r['version'] != ap['replaces_revision']), None)
            view = {'amendment_id': a['id'], 'amendment_version': a['version'],
                    'source_sha256': a['source'], 'report_id': report_id,
                    'issued_on': ap['issued_on'], 'prediction_week': ap['prediction_week'],
                    'replaces_revision': ap['replaces_revision']}
            if target is None:
                view['status'] = 'unverifiable'
                view['detail'] = (
                    f"修订声明替换 {report_id} 的 {ap['replaces_revision']} 版，"
                    "但被替换的报告原文尚未取得，无法核对修订对象")
            elif successor is None:
                view['status'] = 'pending'
                view['detail'] = (
                    f"修订说明已到：{report_id} 的 {ap['replaces_revision']} 版预测期将改为 "
                    f"{ap['prediction_week']}；承载该观点的新版报告原文尚未取得，"
                    f"{ap['replaces_revision']} 版只能作为已被修订的历史预测，不能视为现行观点")
            elif successor['payload'].get('prediction_week') != ap['prediction_week']:
                view['status'] = 'inconsistent'
                view['detail'] = (
                    f"修订说明指向预测期 {ap['prediction_week']}，但新版报告 "
                    f"{successor['version']} 声明预测期 {successor['payload']['prediction_week']}，两者不一致，待核")
            else:
                view['status'] = 'fulfilled'
                view['fulfilled_by_report'] = successor['version']
                view['detail'] = (
                    f"修订已由新版报告 {successor['version']} 落实：预测期 "
                    f"{ap['replaces_revision']} 版 → {ap['prediction_week']}")
                verified_digests.add(a['source'])
            amendment_views.append(view)

        # 每个被修订指向的报告版次 -> 修订状态，状态按版次精确归属。
        amendment_by_target = {}
        for a, v in zip(study_amendments, amendment_views):
            amendment_by_target[a['payload']['replaces_revision']] = v
        replaced = {ver for ver, v in amendment_by_target.items() if v['status'] == 'fulfilled'}
        pending_amendments = [v for v in amendment_views
                              if v['status'] in ('pending', 'unverifiable', 'inconsistent')]

        # 报告版本分类：被已落实修订替换的是历史版本；被悬置修订指向的版次等待新版；其余最新版为当前预测。
        report_views = []
        current = None
        for r in study_reports:
            p = r['payload']
            citations = []
            for s in study_spots:
                sp = s['payload']
                if sp['observed_week'] < p['prediction_week']:
                    citations.append({
                        'spot_id': s['id'], 'spot_version': s['version'],
                        'source_sha256': s['source'],
                        'observed_week': sp['observed_week'],
                        'price_cny_kg': sp['price_cny_kg'],
                        'relation': '报告发布时引用的此前现货观察；仅支持其观察周事实，不验证预测周'})
            own_amendment = amendment_by_target.get(r['version'])
            if r['version'] in replaced:
                status, detail = 'superseded', f"该版本已被修订并由后续报告替换，属于历史预测（预测期 {p['prediction_week']}）"
            elif own_amendment is not None and own_amendment['status'] in ('pending', 'inconsistent'):
                status, detail = 'revision_pending', own_amendment['detail']
            elif any(v['status'] == 'inconsistent' for v in amendment_views):
                status, detail = 'disputed', (
                    f"存在与修订说明不一致的在途修订，该版本（预测期 {p['prediction_week']}）能否作为现行观点待核")
            else:
                status, detail = 'current', f"当前可查的最新报告版本；预测期 {p['prediction_week']} 属于未来预测，尚待该周现货观察证实"
            view = {'report_id': report_id, 'report_version': r['version'],
                    'source_sha256': r['source'], 'prediction_week': p['prediction_week'],
                    'issued_on': p['issued_on'], 'status': status, 'status_detail': detail,
                    'spot_citations': citations}
            report_views.append(view)
            if status == 'current':
                current = view

        study_pending = []
        if not study_reports:
            study_pending.append({
                'relation': 'report_missing', 'report_id': report_id,
                'detail': f"已收到关联 report_id={report_id} 的资料，但机构报告原文缺失，预测观点无法呈现"})
        if pending_amendments:
            for a in pending_amendments:
                study_pending.append({'relation': 'amendment_awaits_report', 'report_id': report_id,
                                      'amendment_id': a['amendment_id'], 'detail': a['detail']})
        if study_reports and current is not None:
            same_week = [s for s in study_spots
                         if s['payload']['observed_week'] == current['prediction_week']]
            if not same_week:
                study_pending.append({
                    'relation': 'prediction_without_observation', 'report_id': report_id,
                    'report_version': current['report_version'],
                    'prediction_week': current['prediction_week'],
                    'detail': (
                        f"预测期 {current['prediction_week']} 的现货实绩尚未观察/取得，"
                        "当前预测不能标记为已证实；已引用现货仅支持各自观察周")})
        if not any(rv['spot_citations'] for rv in report_views):
            if not study_spots:
                detail = '报告引用的现货表原文尚未取得，事实依据待核；报告原文仍按来源原话保留'
            else:
                detail = (
                    f"已收现货表的观察周（{', '.join(sorted(s['payload']['observed_week'] for s in study_spots))}）"
                    "均不早于报告预测周或未被任何报告版本引用，引用关系待核")
            study_pending.append({
                'relation': 'spot_reference_missing', 'report_id': report_id, 'detail': detail})

        # 连贯状态下的资料才计入已核实：现货被某版本报告实际引用；当前预测有引用且无悬置修订。
        for rv in report_views:
            for cit in rv['spot_citations']:
                verified_digests.add(cit['source_sha256'])
        if current is not None and current['spot_citations'] and not pending_amendments:
            verified_digests.add(current['source_sha256'])

        for item in study_pending:
            if item['relation'] in ('amendment_awaits_report', 'report_missing', 'spot_reference_missing'):
                blocking.append(item['detail'])
            all_pending.append(item)

        studies.append({
            'report_id': report_id,
            'current_prediction': (None if (pending_amendments or current is None) else {
                'report_version': current['report_version'], 'source_sha256': current['source_sha256'],
                'prediction_week': current['prediction_week'], 'issued_on': current['issued_on'],
                'nature': '未来预测：预测周现货观察取得前不属于已核实事实'}),
            'report_versions': report_views,
            'amendments': amendment_views,
            'pending_relations': study_pending})

    # 兼容既有发布判定：事实与当前预测引用链完整且无悬置修订才发布；待核关系不隐藏资料。
    publishable = bool(studies) and not blocking and all(
        s['current_prediction'] is not None
        and any(rv['spot_citations'] for rv in s['report_versions'])
        for s in studies)

    # 保留既有 matched_pairs 结构（仅作为“报告引用此前现货”的线索），并补全期间字段。
    pairs = []
    for first in reports:
        for second in spots:
            a, b = first['payload'], second['payload']
            if a['report_id'] == b['report_id'] and b['observed_week'] < a['prediction_week']:
                pairs.append({'left_id': first['id'], 'left_version': first['version'],
                              'right_id': second['id'], 'right_version': second['version'],
                              'left_source': first['source'], 'right_source': second['source'],
                              'prediction_week': a['prediction_week'],
                              'observed_week': b['observed_week'],
                              'relation': '现货观察周早于报告预测周：可作引用依据，不构成预测实绩'})

    return {
        'publishable': publishable,
        'reasons': [] if publishable else (blocking or ['机构观点引用此前现货观察期，或存在待核来源关系']),
        'received_types': sorted({r['type'] for r in rows}),
        'received_versions': len(rows),
        'matched_pairs': pairs,
        'candidate_relations': sorted({str(r['payload'].get(CONTRACT['relation_field'])) for r in rows}),
        'spot_facts': spot_facts,
        'studies': studies,
        'pending_relations': all_pending,
        'verified_digests': sorted(verified_digests)}

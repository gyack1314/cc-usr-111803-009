"""只读重放合成的来源交互并展示当前接收状态与冻结原文。"""
import argparse
import json
from .transport import Replay
from .ledger import connect, receive, raw_receipt
from .view import overview


def _load(connection, collection, manifest):
    replay = Replay(manifest)
    for step in replay.steps:
        request = step['request']
        raw, receipt = replay.request(request['method'], request['url'])
        receive(connection, collection, raw, receipt)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['inspect', 'receipt'])
    p.add_argument('manifest')
    p.add_argument('body_sha256', nargs='?', help='receipt 子命令：要查看的原文收据 sha256')
    p.add_argument('--collection', default='pork-009')
    args = p.parse_args()
    db = connect(':memory:')
    _load(db, args.collection, args.manifest)
    if args.command == 'inspect':
        print(json.dumps(overview(db, args.collection), ensure_ascii=False, indent=2))
    else:
        if not args.body_sha256:
            raise SystemExit('receipt 子命令需要提供 body_sha256')
        receipt = raw_receipt(db, args.collection, args.body_sha256)
        print(json.dumps({k: (v.decode('utf-8') if isinstance(v, bytes) else v)
                          for k, v in receipt.items()}, ensure_ascii=False, indent=2))
    db.close()


if __name__ == '__main__':
    main()

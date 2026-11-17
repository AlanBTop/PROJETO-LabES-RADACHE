"""Manutenção explícita: simula expurgo por padrão, sem iniciar servidor ou envios."""
import argparse
import json
import database
import privacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('purge', 'reclassify'))
    parser.add_argument('--days', type=int, default=365)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.command == 'purge':
        print(json.dumps(privacy.purge(args.days, args.apply), ensure_ascii=False))
    elif args.apply:
        print(json.dumps(dict(reclassificadas=database.reclassificar_avaliacoes())))
    else:
        print('Migração histórica explícita; use --apply após revisar e fazer backup.')


if __name__ == '__main__':
    main()

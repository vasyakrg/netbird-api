# netbird_linter.py
#
# This script is used to lint the Netbird configuration files.
# It can be used to check for duplicates, empty groups in policies, and other issues.
#
# Usage:
# python3 netbird_linter.py
#
# Version: 1.0.1
#
import os
import sys
import yaml

RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RESET = '\033[0m'

def check_duplicates_in_dir(entity):
    seen = {}
    duplicates = []
    if not os.path.isdir(entity):
        return []
    for fname in os.listdir(entity):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join(entity, fname), 'r') as f:
                try:
                    configs = list(yaml.safe_load_all(f))
                except Exception as e:
                    print(f"{RED}[LINTER ERROR]{RESET} Ошибка парсинга {fname}: {e}")
                    sys.exit(1)
                for doc in configs:
                    if isinstance(doc, list):
                        for idx, item in enumerate(doc):
                            key = item.get('email') if entity == 'users' else item.get('name')
                            if key:
                                if key in seen:
                                    prev = seen[key]
                                    duplicates.append({
                                        'name': key,
                                        'file1': prev['file'],
                                        'line1': prev['line'],
                                        'file2': fname,
                                        'line2': idx + 1
                                    })
                                else:
                                    seen[key] = {'file': fname, 'line': idx + 1}
                    elif isinstance(doc, dict):
                        key = doc.get('email') if entity == 'users' else doc.get('name')
                        if key:
                            if key in seen:
                                prev = seen[key]
                                duplicates.append({
                                    'name': key,
                                    'file1': prev['file'],
                                    'line1': prev['line'],
                                    'file2': fname,
                                    'line2': 1
                                })
                            else:
                                seen[key] = {'file': fname, 'line': 1}
    return duplicates

def check_empty_groups_in_policies():
    warnings = []
    # Собираем все группы из groups
    groups_data = {}
    if os.path.isdir('groups'):
        for fname in os.listdir('groups'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join('groups', fname), 'r') as f:
                    try:
                        configs = list(yaml.safe_load_all(f))
                    except Exception:
                        continue
                    for doc in configs:
                        if isinstance(doc, list):
                            for g in doc:
                                if g and 'name' in g:
                                    groups_data[g['name']] = g
                        elif isinstance(doc, dict) and 'name' in doc:
                            groups_data[doc['name']] = doc
    # Собираем группы из users.yaml
    users_groups = set()
    users_path = os.path.join('groups', 'users.yaml')
    if os.path.isfile(users_path):
        with open(users_path, 'r') as f:
            try:
                configs = list(yaml.safe_load_all(f))
            except Exception:
                configs = []
            for doc in configs:
                if isinstance(doc, list):
                    for u in doc:
                        # если это user с auto_groups
                        for g in u.get('auto_groups', []):
                            users_groups.add(g)
                        # если это группа (name)
                        if 'name' in u:
                            users_groups.add(u['name'])
                elif isinstance(doc, dict):
                    for g in doc.get('auto_groups', []):
                        users_groups.add(g)
                    if 'name' in doc:
                        users_groups.add(doc['name'])
    # Проверяем все policy
    if os.path.isdir('policy'):
        for fname in os.listdir('policy'):
            if fname == 'users.yaml':
                continue
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join('policy', fname), 'r') as f:
                    try:
                        configs = list(yaml.safe_load_all(f))
                    except Exception:
                        continue
                    for doc in configs:
                        if isinstance(doc, list):
                            for p in doc:
                                _check_policy_groups(p, groups_data, warnings, fname, users_groups)
                        elif isinstance(doc, dict):
                            _check_policy_groups(doc, groups_data, warnings, fname, users_groups)
    return warnings

def _check_policy_groups(policy, groups_data, warnings, fname, users_groups):
    if not policy or 'rules' not in policy:
        return
    for rule in policy['rules']:
        for key in ['sources', 'destinations']:
            if key in rule and isinstance(rule[key], list):
                for group_name in rule[key]:
                    if group_name in users_groups:
                        continue
                    group = groups_data.get(group_name)
                    if group is not None:
                        peers = group.get('peers', [])
                        if not peers:
                            warnings.append(f"{YELLOW}[LINTER WARNING]{RESET} Группа '{group_name}' из policy ({fname}) не содержит пиров")

def main():
    errors = []
    for entity in ['groups', 'policy', 'users', 'dns']:
        dups = check_duplicates_in_dir(entity)
        for d in dups:
            errors.append(
                f"{RED}[LINTER ERROR]{RESET} Дубликат '{d['name']}'\n"
                f"  Папка: {entity}\n"
                f"  1: {d['file1']} (элемент {d['line1']})\n"
                f"  2: {d['file2']} (элемент {d['line2']})"
            )
    warnings = check_empty_groups_in_policies()
    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    if warnings:
        for warn in warnings:
            print(warn)
    print(f"{GREEN}[LINTER ADVICE]{RESET}: ошибок нет.")

if __name__ == '__main__':
    main()

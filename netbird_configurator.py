# netbird_configurator.py
#
# This script is used to configure the Netbird API.
# It can be used to create, update, and delete groups, networks, resources, routes, and policies.
# It can also be used to sync the local directory with the remote API.
#
# Usage:
# python3 netbird_configurator.py
#
# Version: 1.0.1
#

import os
import requests
import yaml
from dotenv import load_dotenv
import time
import argparse

load_dotenv()

API_URL = os.getenv('NETBIRD_API_URL')
API_TOKEN = os.getenv('NETBIRD_API_TOKEN')

HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Content-Type': 'application/json',
}

ENTITY_DIRS = ['groups', 'networks', 'resources', 'routes', 'policies']

RED = '\033[91m'
GREEN = '\033[92m'
RESET = '\033[0m'
DELETE = f"{RED}✗{RESET}"
CREATE = f"{GREEN}+{RESET}"
UPDATE = f"{GREEN}✓{RESET}"
YELLOW = '\033[93m'
RED_MINUS = f"{RED}-{RESET}"

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

def print_spinner(message, spin_idx):
    import sys
    waited = 0
    spin_idx = 0
    spinner = ['|', '/', '-', '\\']
    msg = f"{YELLOW}{message} {spinner[spin_idx % len(spinner)]}{RESET}"
    print(f"\r{msg}", end='', flush=True)


def print_debug_request(method, url, headers, body=None):
    if not DEBUG:
        return
    headers_to_print = dict(headers)
    if 'Authorization' in headers_to_print:
        headers_to_print['Authorization'] = 'Bearer ******'
    print(f"{YELLOW}[DEBUG] {method} {url}{RESET}")
    print(f"{YELLOW}[DEBUG] headers: {headers_to_print}{RESET}")
    if body is not None:
        print(f"{YELLOW}[DEBUG] body: {body}{RESET}")

def get_entity_ids_by_names(entity, names):
    if entity == 'resources':
        # Собираем id ресурсов по всем сетям
        name_to_id = {}
        if os.path.isdir('resources'):
            for fname in os.listdir('resources'):
                if fname.endswith('.yaml') or fname.endswith('.yml'):
                    network_name = fname.rsplit('.', 1)[0]
                    network_id = get_entity_ids_by_names('networks', [network_name])
                    if not network_id:
                        continue
                    url = f"{API_URL}/api/networks/{network_id[0]}/resources"
                    resp = requests.get(url, headers=HEADERS)
                    resp.raise_for_status()
                    objs = resp.json()
                    for o in objs:
                        if 'name' in o and 'id' in o:
                            name_to_id[o['name']] = o['id']
        return [name_to_id[name] for name in names if name in name_to_id]
    elif entity == 'dns':
        resp = requests.get(f"{API_URL}/api/dns/nameservers", headers=HEADERS)
        resp.raise_for_status()
        objs = resp.json()
        name_to_id = {o['name']: o['id'] for o in objs}
        return [name_to_id[name] for name in names if name in name_to_id]
    else:
        resp = requests.get(f"{API_URL}/api/{entity}", headers=HEADERS)
        resp.raise_for_status()
        objs = resp.json()
        name_to_id = {o['name']: o['id'] for o in objs}
        return [name_to_id[name] for name in names if name in name_to_id]

def patch_policy_group_names(policy):
    if 'rules' in policy:
        for rule in policy['rules']:
            # sources: всегда группы
            if 'sources' in rule:
                rule['sources'] = get_entity_ids_by_names('groups', rule['sources'])
            # destinations: группы
            if 'destinations' in rule:
                rule['destinations'] = get_entity_ids_by_names('groups', rule['destinations'])
            # destinationResource: ресурс
            if 'destinationResource' in rule:
                # ищем id ресурса по имени (берём первый найденный)
                resource_names = rule['destinationResource']
                if isinstance(resource_names, list):
                    resource_name = resource_names[0]
                else:
                    resource_name = resource_names
                # ищем id ресурса по имени среди всех сетей
                resource_id, resource_type = None, None
                for net_name in os.listdir('resources') if os.path.isdir('resources') else []:
                    if not (net_name.endswith('.yaml') or net_name.endswith('.yml')):
                        continue
                    with open(os.path.join('resources', net_name), 'r') as f:
                        configs = yaml.safe_load(f)
                        if isinstance(configs, list):
                            for r in configs:
                                if r and r.get('name') == resource_name:
                                    resource_id = get_entity_ids_by_names('resources', [resource_name])
                                    resource_type = r.get('type', 'subnet')
                                    break
                        elif isinstance(configs, dict) and configs.get('name') == resource_name:
                            resource_id = get_entity_ids_by_names('resources', [resource_name])
                            resource_type = configs.get('type', 'subnet')
                    if resource_id:
                        break
                if resource_id:
                    rule['destinationResource'] = {'id': resource_id[0], 'type': resource_type or 'subnet'}
                    rule['destinations'] = None
    return policy

def patch_group_peer_names(group):
    if 'peers' in group:
        group['peers'] = get_entity_ids_by_names('peers', group['peers'])
    return group

def create_entity(entity, config):
    if entity == 'groups':
        config = patch_group_peer_names(config)
    if entity == 'policies':
        config = patch_policy_group_names(config)
        url = f"{API_URL}/api/policies"
    elif entity == 'dns/nameservers':
        url = f"{API_URL}/api/dns/nameservers"
    else:
        url = f"{API_URL}/api/{entity}"
    print_debug_request('POST', url, HEADERS, config)
    resp = requests.post(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка создания {entity}: {resp.status_code} {resp.text}")
        return False
    else:
        print(f"{CREATE} {entity} создан: {config.get('name', config.get('id', ''))}")
        return True

def update_entity(entity, entity_id, config):
    if entity == 'groups':
        config = patch_group_peer_names(config)
    if entity == 'policies':
        config = patch_policy_group_names(config)
    if entity == 'dns/nameservers':
        url = f"{API_URL}/api/dns/nameservers/{entity_id}"
    else:
        url = f"{API_URL}/api/{entity}/{entity_id}"
    print_debug_request('PUT', url, HEADERS, config)
    resp = requests.put(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка обновления {entity}: {resp.status_code} {resp.text}")
        return False
    else:
        print(f"{UPDATE} {entity} обновлён: {config.get('name', config.get('id', ''))}")
        return True

def delete_entity(entity, entity_id, name):
    if entity == 'dns/nameservers':
        url = f"{API_URL}/api/dns/nameservers/{entity_id}"
    else:
        url = f"{API_URL}/api/{entity}/{entity_id}"
    print_debug_request('DELETE', url, HEADERS)
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"{DELETE} Ошибка удаления {entity} {name}: {resp.status_code} {resp.text}")
        return False
    else:
        print(f"{RED_MINUS} {entity} удалён: {name}")
        return True

def sync_entity_dir(entity):
    api_entity = 'policies' if entity == 'policy' else entity
    if entity not in ['groups', 'policy', 'users', 'dns']:
        process_entity_dir(entity)
        return
    stats = {'created': 0, 'updated': 0, 'deleted': 0, 'errors': 0}
    print(f"\n=== {entity.upper()} ===")
    if entity == 'users':
        # users: каждый файл — массив пользователей, ключ — email
        if not os.path.isdir('users'):
            return
        for fname in os.listdir('users'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join('users', fname), 'r') as f:
                    configs = yaml.safe_load(f)
                    if not isinstance(configs, list):
                        continue
                    for user in configs:
                        email = user.get('email')
                        if not email:
                            print(f"{DELETE} user без email в {fname}")
                            stats['errors'] += 1
                            continue
                        # auto_groups: преобразуем имена в id
                        if 'auto_groups' in user:
                            group_ids = get_entity_ids_by_names('groups', user['auto_groups'])
                            if len(group_ids) != len(user['auto_groups']):
                                print(f"{DELETE} Не найдены все группы для user {email}: {user['auto_groups']}")
                                stats['errors'] += 1
                                continue
                            user['auto_groups'] = group_ids
                        # ищем id по email
                        resp = requests.get(f"{API_URL}/api/users", headers=HEADERS)
                        resp.raise_for_status()
                        users_api = resp.json()
                        user_id = None
                        for u in users_api:
                            if u.get('email') == email:
                                user_id = u['id']
                                break
                        if not user_id:
                            print(f"{DELETE} Не найден user по email: {email}")
                            stats['errors'] += 1
                            continue
                        update_entity('users', user_id, user)
                        stats['updated'] += 1
        print(f"--- ИТОГИ USERS ---")
        print(f"{UPDATE} Обновлено: {stats['updated']}")
        if stats['errors']:
            print(f"{DELETE} Ошибок: {stats['errors']}")
        print()
        return
    if entity == 'dns':
        if not os.path.isdir('dns'):
            return
        # Получаем все существующие dns группы из API
        resp = requests.get(f"{API_URL}/api/dns/nameservers", headers=HEADERS)
        resp.raise_for_status()
        remote_objs = resp.json()
        remote_by_name = {g['name']: g for g in remote_objs}
        remote_names = set(remote_by_name.keys())
        local_names = set()
        local_configs = {}
        for fname in os.listdir('dns'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join('dns', fname), 'r') as f:
                    obj = yaml.safe_load(f)
                    if not isinstance(obj, dict) or 'name' not in obj:
                        continue
                    if 'groups' in obj:
                        group_ids = get_entity_ids_by_names('groups', obj['groups'])
                        if len(group_ids) != len(obj['groups']):
                            print(f"{DELETE} Не найдены все группы для dns {obj.get('name')}: {obj['groups']}")
                            stats['errors'] += 1
                            continue
                        obj['groups'] = group_ids
                    local_names.add(obj['name'])
                    local_configs[obj['name']] = obj
        # Создание и обновление
        for name in local_names:
            if name in remote_names:
                print(f"{UPDATE} dns: {name}")
                try:
                    update_entity('dns/nameservers', remote_by_name[name]['id'], local_configs[name])
                    stats['updated'] += 1
                except Exception as e:
                    print(f"{DELETE} Ошибка обновления dns: {e}")
                    stats['errors'] += 1
            else:
                print(f"{CREATE} dns: {name}")
                try:
                    create_entity('dns/nameservers', local_configs[name])
                    stats['created'] += 1
                except Exception as e:
                    print(f"{DELETE} Ошибка создания dns: {e}")
                    stats['errors'] += 1
        # Удаление
        for name in remote_names - local_names:
            print(f"{DELETE} Удаляю dns: {name}")
            try:
                delete_entity('dns/nameservers', remote_by_name[name]['id'], name)
                stats['deleted'] += 1
            except Exception as e:
                print(f"{DELETE} Ошибка удаления dns: {e}")
                stats['errors'] += 1
        print(f"--- ИТОГИ DNS ---")
        print(f"{CREATE} Создано: {stats['created']}")
        print(f"{UPDATE} Обновлено: {stats['updated']}")
        print(f"{RED_MINUS} Удалено: {stats['deleted']}")
        if stats['errors']:
            print(f"{DELETE} Ошибок: {stats['errors']}")
        print()
        return
    resp = requests.get(f"{API_URL}/api/{api_entity}", headers=HEADERS)
    resp.raise_for_status()
    remote_objs = resp.json()
    remote_by_name = {g['name']: g for g in remote_objs}
    remote_names = set(remote_by_name.keys())
    local_names = set()
    local_configs = {}
    if os.path.isdir(entity):
        for fname in os.listdir(entity):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join(entity, fname), 'r') as f:
                    configs = yaml.safe_load(f)
                    if entity == 'groups' or entity == 'dns':
                        if isinstance(configs, list):
                            for config in configs:
                                if config and 'name' in config:
                                    local_names.add(config['name'])
                                    local_configs[config['name']] = config
                        elif isinstance(configs, dict) and 'name' in configs:
                            local_names.add(configs['name'])
                            local_configs[configs['name']] = configs
                    elif entity == 'policy':
                        if isinstance(configs, list):
                            for config in configs:
                                if config and 'name' in config:
                                    local_names.add(config['name'])
                                    local_configs[config['name']] = config
                        elif isinstance(configs, dict) and 'name' in configs:
                            local_names.add(configs['name'])
                            local_configs[configs['name']] = configs
                    else:
                        if isinstance(configs, dict) and 'name' in configs:
                            local_names.add(configs['name'])
                            local_configs[configs['name']] = configs
    for name in local_names - remote_names:
        if name.upper() == 'ALL':
            continue
        print(f"Создаю {entity[:-1]}: {name}")
        try:
            ok = False
            if entity == 'policy':
                # применяем каждую политику отдельно
                ok = create_entity('policies', local_configs[name])
            elif entity == 'dns':
                ok = create_entity('dns/nameservers', local_configs[name])
            else:
                ok = create_entity(entity, local_configs[name])
            if ok:
                stats['created'] += 1
            else:
                stats['errors'] += 1
        except Exception as e:
            print(f"{DELETE} Ошибка создания: {e}")
            stats['errors'] += 1
    for name in remote_names - local_names:
        if name.upper() == 'ALL':
            continue
        print(f"Удаляю {entity[:-1]}: {name}")
        try:
            ok = False
            if entity == 'groups':
                ok = delete_entity(entity, remote_by_name[name]['id'], name)
            elif entity == 'policy':
                ok = delete_entity('policies', remote_by_name[name]['id'], name)
            elif entity == 'dns':
                ok = delete_entity('dns/nameservers', remote_by_name[name]['id'], name)
            if ok:
                stats['deleted'] += 1
            else:
                stats['errors'] += 1
        except Exception as e:
            print(f"{DELETE} Ошибка удаления: {e}")
            stats['errors'] += 1
    for name in local_names & remote_names:
        if name.upper() == 'ALL':
            continue
        print(f"Обновляю: {name}")
        try:
            ok = False
            if entity == 'groups':
                ok = update_entity(entity, remote_by_name[name]['id'], local_configs[name])
            elif entity == 'policy':
                ok = update_entity('policies', remote_by_name[name]['id'], local_configs[name])
            elif entity == 'dns':
                ok = update_entity('dns/nameservers', remote_by_name[name]['id'], local_configs[name])
            if ok:
                stats['updated'] += 1
            else:
                stats['errors'] += 1
        except Exception as e:
            print(f"{DELETE} Ошибка обновления: {e}")
            stats['errors'] += 1
    print(f"--- ИТОГИ {entity.upper()} ---")
    print(f"{CREATE} Создано: {stats['created']}")
    print(f"{UPDATE} Обновлено: {stats['updated']}")
    print(f"{RED_MINUS} Удалено: {stats['deleted']}")
    if stats['errors']:
        print(f"{DELETE} Ошибок: {stats['errors']}")
    print()

def process_entity_dir(entity):
    if not os.path.isdir(entity):
        return
    for fname in os.listdir(entity):
        if fname.endswith('.yaml') or fname.endswith('.yml'):
            with open(os.path.join(entity, fname), 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, dict):
                    create_entity(entity, configs)

def get_network_id_by_name(name):
    ids = get_entity_ids_by_names('networks', [name])
    return ids[0] if ids else None

def create_resource(config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для ресурса: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/resources"
    print_debug_request('POST', url, HEADERS, config)
    resp = requests.post(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка создания resource: {resp.status_code} {resp.text}")
    else:
        print(f"{CREATE} resource создан: {config.get('name', config.get('id', ''))}")

def update_resource(resource_id, config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для ресурса: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/resources/{resource_id}"
    print_debug_request('PUT', url, HEADERS, config)
    resp = requests.put(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка обновления resource: {resp.status_code} {resp.text}")
    else:
        print(f"{UPDATE} resource обновлён: {config.get('name', config.get('id', ''))}")

def delete_resource(resource_id, config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для ресурса: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/resources/{resource_id}"
    print_debug_request('DELETE', url, HEADERS)
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"{DELETE} Ошибка удаления resource {config.get('name')}: {resp.status_code} {resp.text}")
    else:
        print(f"{DELETE} resource удалён: {config.get('name')}")

def create_route(config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для роутера: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/routers"
    print_debug_request('POST', url, HEADERS, config)
    resp = requests.post(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка создания route: {resp.status_code} {resp.text}")
    else:
        print(f"{CREATE} route создан: {config.get('name', config.get('id', ''))}")

def update_route(route_id, config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для роутера: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/routers/{route_id}"
    print_debug_request('PUT', url, HEADERS, config)
    resp = requests.put(url, headers=HEADERS, json=config)
    if resp.status_code not in (200, 201):
        print(f"{DELETE} Ошибка обновления route: {resp.status_code} {resp.text}")
    else:
        print(f"{UPDATE} route обновлён: {config.get('name', config.get('id', ''))}")

def delete_route(route_id, config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для роутера: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/routers/{route_id}"
    print_debug_request('DELETE', url, HEADERS)
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"{DELETE} Ошибка удаления route {config.get('name')}: {resp.status_code} {resp.text}")
    else:
        print(f"{DELETE} route удалён: {config.get('name')}")

def patch_resource_group_names(resource):
    if 'groups' in resource:
        resource['groups'] = get_entity_ids_by_names('groups', resource['groups'])
    return resource

def patch_route_peer_groups(route):
    if 'peer_groups' in route:
        route['peer_groups'] = get_entity_ids_by_names('groups', route['peer_groups'])
    return route

def sync_groups():
    sync_entity_dir('groups')

def sync_networks():
    print(f"\n=== NETWORKS ===")
    # Получаем все networks из API
    resp = requests.get(f"{API_URL}/api/networks", headers=HEADERS)
    resp.raise_for_status()
    remote_objs = resp.json()
    remote_by_name = {g['name']: g for g in remote_objs}
    remote_names = set(remote_by_name.keys())
    # Читаем все networks из файлов (массив или объект)
    local_names = set()
    local_configs = {}
    if os.path.isdir('networks'):
        for fname in os.listdir('networks'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                with open(os.path.join('networks', fname), 'r') as f:
                    configs = yaml.safe_load(f)
                    if isinstance(configs, list):
                        for config in configs:
                            if config and 'name' in config:
                                local_names.add(config['name'])
                                local_configs[config['name']] = config
                    elif isinstance(configs, dict) and 'name' in configs:
                        local_names.add(configs['name'])
                        local_configs[configs['name']] = configs
    # Создаём недостающие
    for name in local_names - remote_names:
        print(f"{CREATE} network: {name}")
        create_entity('networks', local_configs[name])
    # Обновляем существующие
    for name in local_names & remote_names:
        print(f"{UPDATE} network: {name}")
        update_entity('networks', remote_by_name[name]['id'], local_configs[name])
    # Не удаляем лишние на этом этапе
    print(f"--- ИТОГИ NETWORKS ---")
    print(f"{CREATE} Создано: {len(local_names - remote_names)}")
    print(f"{UPDATE} Обновлено: {len(local_names & remote_names)}")
    print()
    return remote_by_name, local_names

def create_or_update_resource(config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для ресурса: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/resources"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    remote_resources = resp.json() or []
    remote_by_name = {r['name']: r for r in remote_resources if r and 'name' in r}
    config = patch_resource_group_names(config)
    if config['name'] in remote_by_name:
        print(f"{UPDATE} resource: {config['name']} в сети {config['network']}")
        update_resource(remote_by_name[config['name']]['id'], config)
    else:
        print(f"{CREATE} resource: {config['name']} в сети {config['network']}")
        create_resource(config)

def create_or_update_route(config):
    network_id = get_network_id_by_name(config['network'])
    if not network_id:
        print(f"{DELETE} Не найден network для роутера: {config.get('name')}")
        return
    url = f"{API_URL}/api/networks/{network_id}/routers"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    remote_routes = resp.json() or []
    config = patch_route_peer_groups(config)
    # Сравниваем только по peer_groups (сортируем для надёжности)
    config_peer_groups = sorted(config.get('peer_groups', []) or [])
    found = None
    for r in remote_routes:
        if sorted(r.get('peer_groups', []) or []) == config_peer_groups:
            found = r
            break
    if found:
        print(f"{UPDATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
        update_route(found['id'], config)
    else:
        print(f"{CREATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
        create_route(config)

def sync_resources_and_routes(remote_networks):
    stats_resources = {'created': 0, 'updated': 0, 'errors': 0}
    stats_routes = {'created': 0, 'updated': 0, 'errors': 0}
    # resources
    if os.path.isdir('resources'):
        for fname in os.listdir('resources'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                network_name = fname.rsplit('.', 1)[0]
                if network_name not in remote_networks:
                    print(f"{DELETE} Пропускаю resource: не найден network {network_name}")
                    continue
                with open(os.path.join('resources', fname), 'r') as f:
                    configs = yaml.safe_load(f)
                    if not configs:
                        continue
                    if isinstance(configs, list):
                        for config in configs:
                            if not config or 'name' not in config:
                                continue
                            config = dict(config, network=network_name)
                            # считаем результат
                            network_id = get_network_id_by_name(config['network'])
                            if not network_id:
                                stats_resources['errors'] += 1
                                continue
                            url = f"{API_URL}/api/networks/{network_id}/resources"
                            resp = requests.get(url, headers=HEADERS)
                            resp.raise_for_status()
                            remote_resources = resp.json() or []
                            remote_by_name = {r['name']: r for r in remote_resources if r and 'name' in r}
                            config = patch_resource_group_names(config)
                            if config['name'] in remote_by_name:
                                print(f"{UPDATE} resource: {config['name']} в сети {config['network']}")
                                update_resource(remote_by_name[config['name']]['id'], config)
                                stats_resources['updated'] += 1
                            else:
                                print(f"{CREATE} resource: {config['name']} в сети {config['network']}")
                                create_resource(config)
                                stats_resources['created'] += 1
                    elif isinstance(configs, dict) and 'name' in configs:
                        config = dict(configs, network=network_name)
                        network_id = get_network_id_by_name(config['network'])
                        if not network_id:
                            stats_resources['errors'] += 1
                        else:
                            url = f"{API_URL}/api/networks/{network_id}/resources"
                            resp = requests.get(url, headers=HEADERS)
                            resp.raise_for_status()
                            remote_resources = resp.json() or []
                            remote_by_name = {r['name']: r for r in remote_resources if r and 'name' in r}
                            config = patch_resource_group_names(config)
                            if config['name'] in remote_by_name:
                                print(f"{UPDATE} resource: {config['name']} в сети {config['network']}")
                                update_resource(remote_by_name[config['name']]['id'], config)
                                stats_resources['updated'] += 1
                            else:
                                print(f"{CREATE} resource: {config['name']} в сети {config['network']}")
                                create_resource(config)
                                stats_resources['created'] += 1
    # routes
    if os.path.isdir('routes'):
        for fname in os.listdir('routes'):
            if fname.endswith('.yaml') or fname.endswith('.yml'):
                network_name = fname.rsplit('.', 1)[0]
                if network_name not in remote_networks:
                    print(f"{DELETE} Пропускаю route: не найден network {network_name}")
                    continue
                with open(os.path.join('routes', fname), 'r') as f:
                    configs = yaml.safe_load(f)
                    if not configs:
                        continue
                    if isinstance(configs, list):
                        for config in configs:
                            if not config or 'name' not in config:
                                continue
                            config = dict(config, network=network_name)
                            network_id = get_network_id_by_name(config['network'])
                            if not network_id:
                                stats_routes['errors'] += 1
                                continue
                            url = f"{API_URL}/api/networks/{network_id}/routers"
                            resp = requests.get(url, headers=HEADERS)
                            resp.raise_for_status()
                            remote_routes = resp.json() or []
                            config = patch_route_peer_groups(config)
                            config_peer_groups = sorted(config.get('peer_groups', []) or [])
                            found = None
                            for r in remote_routes:
                                if sorted(r.get('peer_groups', []) or []) == config_peer_groups:
                                    found = r
                                    break
                            if found:
                                print(f"{UPDATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
                                update_route(found['id'], config)
                                stats_routes['updated'] += 1
                            else:
                                print(f"{CREATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
                                create_route(config)
                                stats_routes['created'] += 1
                    elif isinstance(configs, dict) and 'name' in configs:
                        config = dict(configs, network=network_name)
                        network_id = get_network_id_by_name(config['network'])
                        if not network_id:
                            stats_routes['errors'] += 1
                        else:
                            url = f"{API_URL}/api/networks/{network_id}/routers"
                            resp = requests.get(url, headers=HEADERS)
                            resp.raise_for_status()
                            remote_routes = resp.json() or []
                            config = patch_route_peer_groups(config)
                            config_peer_groups = sorted(config.get('peer_groups', []) or [])
                            found = None
                            for r in remote_routes:
                                if sorted(r.get('peer_groups', []) or []) == config_peer_groups:
                                    found = r
                                    break
                            if found:
                                print(f"{UPDATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
                                update_route(found['id'], config)
                                stats_routes['updated'] += 1
                            else:
                                print(f"{CREATE} route (peer_groups={config_peer_groups}) в сети {config['network']}")
                                create_route(config)
                                stats_routes['created'] += 1
    print(f"--- ИТОГИ RESOURCES ---")
    print(f"{CREATE} Создано: {stats_resources['created']}")
    print(f"{UPDATE} Обновлено: {stats_resources['updated']}")
    if stats_resources['errors']:
        print(f"{DELETE} Ошибок: {stats_resources['errors']}")
    print()
    print(f"--- ИТОГИ ROUTES ---")
    print(f"{CREATE} Создано: {stats_routes['created']}")
    print(f"{UPDATE} Обновлено: {stats_routes['updated']}")
    if stats_routes['errors']:
        print(f"{DELETE} Ошибок: {stats_routes['errors']}")
    print()

def delete_absent_networks(remote_networks, local_network_names):
    for name, net in remote_networks.items():
        if name not in local_network_names:
            print(f"{DELETE} Удаляю network: {name}")
            delete_entity('networks', net['id'], name)

def wait_for_networks_ready(local_network_names, timeout=30, interval=3):
    while True:
        found_ids = get_entity_ids_by_names('networks', list(local_network_names))
        if len(found_ids) == len(local_network_names):
            print(f"\r{GREEN}Все сети появились в API, продолжаем...{' ' * 30}{RESET}")
            break
        print_spinner("Ожидание появления всех сетей в API...", spin_idx)
        spin_idx += 1
        time.sleep(interval)
        waited += interval
        if waited >= timeout:
            print(f"\r{RED}Таймаут ожидания сетей!{' ' * 30}{RESET}")
            sys.exit(1)

def cleanup_resources(remote_networks):
    if not os.path.isdir('resources'):
        return
    for network_name, net in remote_networks.items():
        network_id = net['id']
        url = f"{API_URL}/api/networks/{network_id}/resources"
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        remote_resources = resp.json() or []
        remote_by_name = {r['name']: r for r in remote_resources if r and 'name' in r}
        local_names = set()
        fname = f"resources/{network_name}.yaml"
        if os.path.isfile(fname):
            with open(fname, 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for config in configs:
                        if config and 'name' in config:
                            local_names.add(config['name'])
                elif isinstance(configs, dict) and 'name' in configs:
                    local_names.add(configs['name'])
        for name, r in remote_by_name.items():
            if name not in local_names:
                print(f"{DELETE} Удаляю resource: {name} в сети {network_name}")
                delete_resource(r['id'], {'network': network_name, 'name': name})

def cleanup_routes(remote_networks):
    if not os.path.isdir('routes'):
        return
    for network_name, net in remote_networks.items():
        network_id = net['id']
        url = f"{API_URL}/api/networks/{network_id}/routers"
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        remote_routes = resp.json() or []
        remote_by_peer_groups = {tuple(sorted(r.get('peer_groups', []))): r for r in remote_routes if r and 'peer_groups' in r}
        local_peer_groups = set()
        fname = f"routes/{network_name}.yaml"
        if os.path.isfile(fname):
            with open(fname, 'r') as f:
                configs = yaml.safe_load(f)
                if isinstance(configs, list):
                    for config in configs:
                        if config and 'peer_groups' in config:
                            local_peer_groups.add(tuple(sorted(get_entity_ids_by_names('groups', config['peer_groups']))))
                elif isinstance(configs, dict) and 'peer_groups' in configs:
                    local_peer_groups.add(tuple(sorted(get_entity_ids_by_names('groups', configs['peer_groups']))))
        for peer_groups, r in remote_by_peer_groups.items():
            if peer_groups not in local_peer_groups:
                print(f"{DELETE} Удаляю route (peer_groups={list(peer_groups)}) в сети {network_name}")
                delete_route(r['id'], {'network': network_name, 'name': r.get('name', ''), 'peer_groups': list(peer_groups)})

def cleanup_all(remote_networks, local_network_names):
    delete_absent_networks(remote_networks, local_network_names)
    cleanup_resources(remote_networks)
    cleanup_routes(remote_networks)

def main():
    parser = argparse.ArgumentParser(description='Netbird Configurator')
    parser.add_argument('--tag', type=str, default='all', help='Тег действия: all, groups, users, dns, networks, resources, routes, policy, cleanup')
    args = parser.parse_args()
    tag = args.tag

    if tag == 'all' or tag == 'groups':
        sync_groups()
    if tag == 'all' or tag == 'users':
        sync_entity_dir('users')
    if tag == 'all' or tag == 'dns':
        sync_entity_dir('dns')
    if tag == 'all' or tag == 'networks':
        remote_networks, local_network_names = sync_networks()
        wait_for_networks_ready(local_network_names)
    else:
        # если не networks, но нужны для других этапов
        remote_networks, local_network_names = None, None
        if os.path.isdir('networks'):
            remote_networks, local_network_names = sync_networks()
    if tag == 'all':
        sync_resources_and_routes(remote_networks)
    else:
        if tag == 'resources':
            sync_resources_and_routes(remote_networks)
        if tag == 'routes':
            sync_resources_and_routes(remote_networks)
    if tag == 'all' or tag == 'policy':
        sync_entity_dir('policy')
    if tag == 'all' or tag == 'cleanup':
        if remote_networks is None or local_network_names is None:
            remote_networks, local_network_names = sync_networks()
        cleanup_all(remote_networks, local_network_names)

if __name__ == '__main__':
    main()

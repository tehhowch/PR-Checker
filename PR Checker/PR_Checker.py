# Python script to review all of the authenticated user's open Pull Requests,
# and then determine which ones have merge conflicts.
import json
import pprint
import requests
from requests import Session, Response
from urllib.parse import quote_plus
import time

BASE = 'https://api.github.com'

def get_authed_requests(auth_info: dict) -> Session:
    if not auth_info:
        raise ValueError("Missing auth info")
    new_session = requests.Session()
    new_session.headers.update({'Authorization': f'token {auth_info["token"]}'})
    return new_session


def load_user_info() -> dict:
    try:
        with open('git_info.txt', 'r') as file:
            return json.load(file)
    except (FileNotFoundError, ValueError) as err:
        pass
    return {}


def get_user(session: Session) -> dict:
    if not session:
        raise ValueError
    url = BASE + '/user'
    response = session.get(url)
    return response.json()


def get_repos(session: Session) -> list:
    if not session:
        return []
    url = BASE + '/user/repos'
    results = []
    while True:
        response: Response = session.get(url)
        if response.status_code is 200:
            results.extend(response.json())
        if 'next' in response.links:
            url = response.links['next']['url'];
        else:
            break
    return results


def get_open_prs(user: dict, session: Session) -> list:
    if not user or not session:
        return []
    results = []
    q_params = {'state': 'open', 'author': user['login'], 'type': 'pr'}
    q = ' '.join(['{}:{}'.format(k, v) for [k, v] in q_params.items()])
    url = '{}/search/issues?q={}'.format(BASE, quote_plus(q))
    while url:
        response: Response = session.get(url)
        if response.status_code is 200:
            data = response.json()
            results.extend(data['items'])
        if 'next' in response.links:
            url = response.links['next']['url'];
        else:
            break
    return results


def request_pr_status(pull: dict, session: Session):
    if not pull or not session:
        raise ValueError
    url = pull['pull_request']['url']
    response: Response = session.get(url)
    if response.status_code is 200:
        data = response.json()
        if 'mergeable' in data and data['mergeable'] is not 'null':
            return {'completed': True, 'mergeable': data['mergeable'], 'pr': data}
        return {'completed': False}
    response.raise_for_status()
    return {'completed': None}


if __name__ == '__main__':
    auth = load_user_info()
    conflicted = []
    report = []
    with get_authed_requests(auth) as s:
        user = get_user(s)
        prs = get_open_prs(user, s)
        remaining = prs.copy()
        while remaining:
            for pr in remaining:
                status = request_pr_status(pr, s)
                if status['completed'] is True:
                    if status['mergeable'] is False:
                        conflicted.append(status['pr'])
                    remaining.remove(pr)
            if remaining and len(prs) < 1000:
                time.sleep(1. - .001 * len(prs))
        for pr in conflicted:
            pr_report = '#{number}\t{title}\n{html_url}'.format_map(pr)
            pr_report += f'\n{pr["head"]["label"]} @ {pr["head"]["sha"]}\nref {pr["base"]["ref"]} @ {pr["base"]["sha"]} ({pr["commits"]} commits)'
            report.append(pr_report)
        print('\n\n'.join(report))
        pprint.pprint(s.get('{}/rate_limit'.format(BASE)).json()['resources'])
    with open('report.txt', 'w') as output:
        message = f'Checked {len(prs)} open PRs, found {len(conflicted)} with merge conflicts:\n'
        message += '\n\n'.join(report)
        output.write(message)
    with open('report_detailed.txt', 'w') as details:
        json.dump(conflicted, details, indent=2)

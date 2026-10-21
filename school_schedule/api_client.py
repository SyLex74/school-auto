# api_client.py
import requests


class ApiError(Exception):
    pass


class SiteApi:
    def __init__(self, base_url: str, api_key: str, timeout: int = 10):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method, path, params=None, json_body=None):
        url = f'{self.base_url}/bot-api{path}'
        try:
            r = requests.request(
                method, url,
                headers={'X-API-Key': self.api_key},
                params=params, json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ApiError(f'network: {e}') from e

        if r.status_code >= 500:
            raise ApiError(f'server {r.status_code}: {r.text[:200]}')

        try:
            data = r.json()
        except ValueError:
            raise ApiError(f'bad json ({r.status_code})')

        if r.status_code >= 400:
            raise ApiError(f'{r.status_code}: {data}')

        return data

    # ---------- справочники ----------

    def search_regions(self, q, limit=50):
        return self._request('GET', '/regions/',
                             params={'q': q, 'limit': limit})['items']

    def search_cities(self, region_id, q, limit=50):
        return self._request('GET', '/cities/',
                             params={'region_id': region_id, 'q': q, 'limit': limit})['items']

    def search_schools(self, city_id, q, limit=20):
        return self._request('GET', '/schools/',
                             params={'city_id': city_id, 'q': q, 'limit': limit})['items']

    # ---------- профиль VK-пользователя ----------

    def get_user(self, vk_id):
        data = self._request('GET', f'/vk-users/{vk_id}/')
        return data.get('profile') if data.get('exists') else None

    def upsert_user(self, vk_id, patch):
        return self._request('PUT', f'/vk-users/{vk_id}/', json_body=patch)['profile']

    def delete_user(self, vk_id):
        self._request('DELETE', f'/vk-users/{vk_id}/')

    # ---------- расписания ----------

    def schedules_by_school(self, school_id):
        return self._request('GET', '/schedules/by-school/',
                             params={'school_id': school_id})['items']

    # ---------- уведомления ----------

    def pending_changes(self):
        return self._request('GET', '/schedule-changes/pending/')['items']

    def subscribers(self, school_id, class_name=''):
        params = {'school_id': school_id}
        if class_name:
            params['class_name'] = class_name
        return self._request('GET', '/subscribers/', params=params)['vk_ids']

    def mark_notified(self, ids):
        if not ids:
            return
        self._request('POST', '/schedule-changes/mark-notified/',
                      json_body={'ids': ids})
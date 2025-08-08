import requests
from Demos.win32ts_logoff_disconnected import username

from SessionManager import SessionManager
BASE_URL = "http://127.0.0.1:5001"
def make_request(method,endpoint,**kwargs):
    session=SessionManager.get_instance()
    headers=kwargs.pop("headers",{})
    headers["Authorization"]=f"Bearer {session.get_access_token()}"

    try:
        print(BASE_URL+endpoint)
        response=requests.request(method,BASE_URL+endpoint,headers=headers,**kwargs)
        if response.json()[1] == 401:
            res=refrech_token()
            if res:
                headers["Authorization"]=f"Bearer {session.get_access_token()}"
                response = requests.request(method,BASE_URL+ endpoint, headers=headers, **kwargs)
                print("make requestttt rsult in refresh",response)
                return response
        return response
    except requests.exceptions.RequestException as e:
        print(e)
        return None


def refrech_token():
    session=SessionManager.get_instance()
    refresh_token=session.get_refresh_token()
    url = BASE_URL+"/auth/refreshtoken"
    headers = {
        "Authorization": f"Bearer {refresh_token}"
    }
    response=requests.get(url,headers=headers)
    if response.json()[1] == 200:
        access_token=response.json()[0].get("access_token")
        username=response.json()[0].get("username")
        role=response.json()[0].get("role")
        session.set_tokens(access_token,refresh_token,username,role)
        return True
    return False




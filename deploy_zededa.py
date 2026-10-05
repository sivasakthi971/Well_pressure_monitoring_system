#!/usr/bin/env python3
"""
ZEDEDA Cloud REST API Deployment Script for zedcontrol.gmwtus.zededa.net
"""

import os
import sys
import json
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TENANT_URL = "https://zedcontrol.gmwtus.zededa.net"
DEFAULT_TOKEN = "zx35fck9:wBMn08P4-Pv2LDeuiOZuaGqsvkSC8Fb9jkfM1DILh-jJdaWSnPDKgSejLO2rWh8rrMPtohdHMGdXSBDNq6LI6LSh-IjsZ9gmXV4TP8Nza5IhKEvRSVTvBwIoIFQKJulItCML14wiZJaa7-SeOi6YOi0Flv46ExbStXUFX-LPHAI="
COMPOSE_FILE = "docker-compose.zededa.yml"
APP_NAME = "ecrioedge02"
PROJECT_NAME = "ecrio-project-02"
NODE_NAME = "ECRIOEDGE01"

class ZededaDeployer:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _request(self, method: str, endpoint: str, payload: dict = None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                body = res.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8")
            print(f"❌ API Error {e.code} ({method} {endpoint}): {err}", file=sys.stderr)
            raise e

    def get_or_create_project(self, name: str):
        print(f"🔍 Fetching Project '{name}'...")
        try:
            res = self._request("GET", "api/v1/projects")
            for p in res.get("list", []):
                if p.get("name") == name:
                    print(f"✅ Found existing Project '{name}' (ID: {p['id']})")
                    return p["id"]
        except Exception as e:
            print(f"⚠️ Error checking project list: {e}")

        print(f"➕ Creating new Project '{name}'...")
        payload = {
            "name": name,
            "title": f"Project {name}",
            "description": "ECRIO Edge Monitoring Project"
        }
        res = self._request("POST", "api/v1/projects", payload)
        project_id = res.get("id")
        print(f"✅ Created Project '{name}' (ID: {project_id})")
        return project_id

    def get_or_create_node(self, node_name: str, project_id: str):
        print(f"🔍 Fetching Edge Node '{node_name}'...")
        try:
            res = self._request("GET", "api/v1/devices")
            for d in res.get("list", []):
                if d.get("name") == node_name:
                    print(f"✅ Found existing Edge Node '{node_name}' (ID: {d['id']})")
                    return d["id"]
        except Exception as e:
            print(f"⚠️ Error checking device list: {e}")

        print(f"➕ Registering new Edge Node '{node_name}'...")
        payload = {
            "name": node_name,
            "title": f"Edge Node {node_name}",
            "description": "ECRIO Field Edge Gateway",
            "projectId": project_id,
            "modelId": "d1ead66d-914c-4dee-8c89-33274d0d8d65",
            "utype": "AMD64",
            "adminState": "ADMIN_STATE_ACTIVE",
            "interfaces": [
                {
                    "intfname": "eth0",
                    "netname": "ecrio-network",
                    "netid": "a164e794-41a3-48b6-9b3e-e84464007151",
                    "intfUsage": "ADAPTER_USAGE_MANAGEMENT",
                    "ztype": "IO_TYPE_ETH"
                },
                {
                    "intfname": "eth1",
                    "netname": "ecrio-network",
                    "netid": "a164e794-41a3-48b6-9b3e-e84464007151",
                    "intfUsage": "ADAPTER_USAGE_MANAGEMENT",
                    "ztype": "IO_TYPE_ETH"
                }
            ]
        }
        res = self._request("POST", "api/v1/devices", payload)
        node_id = res.get("id")
        print(f"✅ Registered Edge Node '{node_name}' (ID: {node_id})")
        return node_id

    def get_or_create_app(self, compose_content: str):
        print(f"🔍 Checking Edge App '{APP_NAME}'...")
        try:
            res = self._request("GET", "api/v1/apps")
            for a in res.get("list", []):
                if a.get("name") == APP_NAME:
                    print(f"✅ Found existing Edge App '{APP_NAME}' (ID: {a['id']})")
                    return a["id"]
        except Exception as e:
            print(f"⚠️ Error checking app list: {e}")

        print(f"📦 Creating Edge App '{APP_NAME}'...")
        payload = {
            "name": APP_NAME,
            "title": "Well Integrity Monitoring System",
            "userDefinedVersion": "1.0.0",
            "deploymentType": "DEPLOYMENT_TYPE_DOCKER_COMPOSE",
            "manifest": {
                "acKind": "DockerCompose",
                "name": APP_NAME,
                "content": compose_content
            }
        }
        res = self._request("POST", "api/v1/apps", payload)
        app_id = res.get("id")
        print(f"✅ Registered Edge App '{APP_NAME}' (ID: {app_id})")
        return app_id

    def deploy_app_instance(self, app_id: str, node_id: str, project_id: str):
        instance_name = f"{APP_NAME}-instance-02"
        print(f"🚀 Deploying App Instance '{instance_name}' to Node ID {node_id}...")
        payload = {
            "name": instance_name,
            "title": "Well Integrity Monitoring Instance 02",
            "appId": app_id,
            "deviceId": node_id,
            "projectId": project_id,
            "activate": True
        }
        try:
            res = self._request("POST", "api/v1/apps/instances", payload)
            print(f"🎉 App Instance '{instance_name}' deployed successfully!")
            return res
        except urllib.error.HTTPError as e:
            if e.code in (400, 409):
                print(f"ℹ️ App instance response: {e}")
            else:
                raise e

def main():
    token = os.getenv("ZEDEDA_API_TOKEN", DEFAULT_TOKEN)
    deployer = ZededaDeployer(TENANT_URL, token)

    if not os.path.exists(COMPOSE_FILE):
        print(f"❌ File '{COMPOSE_FILE}' not found!")
        sys.exit(1)

    with open(COMPOSE_FILE, "r") as f:
        compose_content = f.read()

    print("=======================================================")
    print(f"ZEDEDA Enterprise Deployment: {TENANT_URL}")
    print("=======================================================")

    # 1. Project
    project_id = deployer.get_or_create_project(PROJECT_NAME)

    # 2. Node
    node_id = deployer.get_or_create_node(NODE_NAME, project_id)

    # 3. App
    app_id = deployer.get_or_create_app(compose_content)

    # 4. Instance
    deployer.deploy_app_instance(app_id, node_id, project_id)

    print("\n=======================================================")
    print("✨ ZEDEDA Cloud Deployment Pipeline Finished!")
    print("=======================================================")

if __name__ == "__main__":
    main()

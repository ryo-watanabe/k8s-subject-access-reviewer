import hug
import logging
import datetime

logging.basicConfig(level=logging.DEBUG)

def log(str):
  d = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
  logging.info(" [" + d + "] " + str)

DENY_NAMESPACES = ["kube-system","kube-public"]
ALLOW_CLUSTER_RESOURCES = ["clusterrolebindings"]
DENY_LIST_CLUSTER_RESOURCES = []
TARGET_USERS = ["system:serviceaccount:default:remote-user"]

#-------------------------------------
# REVIEW
#-------------------------------------

@hug.post('/review', versions=1)
def review(body):

    # リクエストログ出力
    log("Request : " + str(body))

    ret = {
        "apiVersion": "authorization.k8s.io/v1beta1",
        "kind": "SubjectAccessReview",
        "status": {
            "allowed": False
        }
    }

    # When user in TARGET-USERS
    if "spec" in body and "user" in body["spec"] and body["spec"]["user"] in TARGET_USERS:
        # Non resource path
        if "nonResourceAttributes" in body["spec"]:
            ret["status"] = {
                "allowed": True
            }

        if "resourceAttributes" in body["spec"]:
            # Get params
            ra = body["spec"]["resourceAttributes"]

            namespace = ""
            if "namespace" in ra:
                namespace = ra["namespace"]

            # Namespaced Resources
            if namespace:
                if namespace not in DENY_NAMESPACES:
                    ret["status"] = {
                        "allowed": True
                    }
                else:
                    ret["status"]["reason"] = "Resources in forbidden namespaces"

            # Cluster resources
            else:

                if "resource" in ra:
                    resource = ra["resource"]

                    verb = ""
                    if "verb" in ra:
                        verb = ra["verb"]

                    name = ""
                    if "name" in ra:
                        name = ra["name"]

                    # Resource is namespace itself
                    if resource == "namespaces" and name:
                        if name not in DENY_NAMESPACES:
                            ret["status"] = {
                                "allowed": True
                            }
                        else:
                            ret["status"]["reason"] = "Forbidden namespace"

                    # List only cluster resources
                    elif verb and verb == "list":
                        if resource not in DENY_LIST_CLUSTER_RESOURCES:
                            ret["status"] = {
                                "allowed": True
                            }
                        else:
                            ret["status"]["reason"] = "List-forbidden cluster resources"

                    # Allowed cluster resources
                    elif resource in ALLOW_CLUSTER_RESOURCES:
                        ret["status"] = {
                            "allowed": True
                        }

                    else:
                        ret["status"]["reason"] = "Not allowed cluster resources"

    log("Response : " + str(ret))

    return ret

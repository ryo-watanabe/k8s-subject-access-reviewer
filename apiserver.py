import hug
import logging
import datetime

logging.basicConfig(level=logging.DEBUG)

def post_log(path, body):
    d = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    logging.info(" [" + d + "] POST " + path + " " + str(body))

DENY_NAMESPACES = ["kube-system","cattle-system","ingress-nginx","kube-public"]
DENY_USERS = ["system:serviceaccount:default:hatoba-user"]

#-------------------------------------
# REVIEW
#-------------------------------------

@hug.post('/review', versions=1)
def review(body):

    # リクエストログ出力
    post_log("/review", body)

    ret = {
        "apiVersion": "authorization.k8s.io/v1beta1",
        "kind": "SubjectAccessReview",
        "status": {
            "allowed": True
        }
    }

    if "apiVersion" not in body or body["apiVersion"] != "authorization.k8s.io/v1beta1":
        ret["status"] = {"allowed": False, "reason": "Review format error"}
        return ret

    if "kind" not in body or body["kind"] != "SubjectAccessReview":
        ret["status"] = {"allowed": False, "reason": "Review format error"}
        return ret

    # Allow Non-Resource requests
    if "spec" in body and "nonResourceAttributes" in body["spec"]:
        return ret

    # Deny DENY-NAMESPACES as DENY-USERS
    if "spec" in body and "user" in body["spec"] and body["spec"]["user"] in DENY_USERS:
        if "resourceAttributes" in body["spec"] and "namespace" in body["spec"]["resourceAttributes"]:
            if body["spec"]["resourceAttributes"]["namespace"] in DENY_NAMESPACES:
                ret["status"] = {
                    "allowed": False,
                    "reason": "User " + body["spec"]["user"] + " cannot access resources in " +
                        body["spec"]["resourceAttributes"]["namespace"]
                }
                return ret

    return ret

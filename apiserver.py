import hug
import logging
import datetime
from env import *
from k8s_pod import *
from k8s_service import *
from k8s_ingress import *
from k8s_namespace import *
from k8s_pv import *
from k8s_rbac import *
from work_server import *
from master_server import *
from utils import *
from cache import *

logging.basicConfig(level=logging.DEBUG)

def post_log(path, body):
    d = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    logging.info(" [" + d + "] POST " + path + " " + str(body))

def get_log(path):
    d = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    logging.info(" [" + d + "] GET " + path)

#-------------------------------------
# POD
#-------------------------------------

@hug.post('/get_pod',  requires=authentication, versions=1)
def get_pod(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_pod", body)

    # キャッシュ
    if namespace == "*":
        cache = get_cache("get_pod_all")
        if cache["returncode"] == 0:
            return cache["json"]
        data = kubectl_get_pod(namespace, KUBECTL_HOST)
        set_cache("get_pod_all", data)
        return data

    # ポッド情報一覧を取得します。
    # namespaceに「*」を指定した場合に全ネームスペースの情報を返します。
    return kubectl_get_pod(namespace, KUBECTL_HOST)

#-------------------------------------
# SERVICE
#-------------------------------------

@hug.post('/get_service',  requires=authentication, versions=1)
def get_service(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_service", body)

    # キャッシュ
    if namespace == "*":
        cache = get_cache("get_service_all")
        if cache["returncode"] == 0:
            return cache["json"]
        data = kubectl_get_service(namespace, KUBECTL_HOST)
        set_cache("get_service_all", data)
        return data

    # サービス情報一覧を取得します。
    # namespaceに「*」を指定した場合に全ネームスペースの情報を返します。
    return kubectl_get_service(namespace, KUBECTL_HOST)

#-------------------------------------
# PV(PVC)
#-------------------------------------

@hug.post('/get_pv',  requires=authentication, versions=1)
def get_pv(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_pv", body)

    # キャッシュ
    if namespace == "*":
        cache = get_cache("get_pv_all", "60")
        if cache["returncode"] == 0:
            return cache["json"]
        data = kubectl_get_pv(namespace, KUBECTL_HOST)
        set_cache("get_pv_all", data)
        return data

    # PVの情報一覧を取得します。
    # namespaceに「*」を指定した場合に全ネームスペースの情報を返します。
    return kubectl_get_pv(namespace, KUBECTL_HOST)

@hug.get('/get_pv_df',  requires=authentication, versions=1)
def get_pv_df():

    # リクエストログ出力
    get_log("/get_pv_df")

    # キャッシュ
    cache = get_cache("get_pv_df", "60")
    if cache["returncode"] == 0:
        return cache["json"]
    data = get_pv_dir_df(KUBECTL_HOST)
    set_cache("get_pv_df", data)
    return data

    # PVディレクトリのdfを取得します。
    # return get_pv_dir_df(KUBECTL_HOST)

@hug.get('/get_pv_lite',  requires=authentication, versions=1)
def get_pv_lite():

    # リクエストログ出力
    get_log("/get_pv_lite")

    # PVの情報一覧を取得します。
    # namespaceに「*」を指定した場合に全ネームスペースの情報を返します。
    return kubectl_get_pv("*", KUBECTL_HOST, False)

@hug.get('/get_pv_dirs',  requires=authentication, versions=1)
def get_pv_dirs():

    # リクエストログ出力
    get_log("/get_pv_dirs")

    # PVの情報一覧を取得します。
    return get_pv_ls(KUBECTL_HOST)

#-------------------------------------
# NAMESPACE
#-------------------------------------

@hug.get('/get_namespace',  requires=authentication, versions=1)
def get_namespace():

    # リクエストログ出力
    get_log("/get_namespace")

    # ネームスペース名一覧を取得します。
    return kubectl_get_namespace(KUBECTL_HOST)

@hug.post('/create_namespace',  requires=authentication, versions=1)
def create_namespace(namespace: hug.types.text, pvsize: hug.types.text="5Gi", log_age: hug.types.text="7d", body=None):

    # リクエストログ出力
    post_log("/create_namespace", body)

    # ネームスペース名が空白を含まないことをチェック
    #（その他のバリデーションはk8s APIが行う）。
    if namespace and namespace.find(' ') >= 0:

        # APIエラーレスポンス（CLEAN）
        return {"returncode":1, "message":"Invalid value (including spaces): " + namespace, "error_stat":"clean" }

    # k8s namespaceを作成します。
    out = kubectl_create_namespace(namespace, KUBECTL_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（同名ネームスペースが存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("already exists") > -1 or out["message"].find("must match the regex") > -1:
            stat = "clean"
        return append_dict( out, { "namespace":namespace, "step":"create_namespace", "error_stat":stat } )

    # ローカルレジストリのBasic認証設定をk8s secretに登録します。
    out = kubectl_create_registry_secret(namespace, KUBECTL_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（CLEAN）
        return append_dict( out, clean_namespace(namespace, "create_registry_secret", "clean") )

    # k5container.netの証明書を登録します。
    out = create_wildcard_secret(namespace, KUBECTL_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（CLEAN）
        return append_dict( out, clean_namespace(namespace, "create_wildcard_secret", "clean") )

    # マスターサーバーの/pv/[namespace] にネームスペースが利用するディスク領域のパスを作成します。
    out = create_pv_dir(namespace, PV_ROOT, MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（CLEAN）
        return append_dict( out, clean_namespace(namespace, "create_pv_dir") )

    # マスターサーバーの/pv/[namespace]/logsに出力されるログの自動削除設定をします。CentOS7のtmpfile機能を利用。
    # ※2017/6/12 ファイルサイズによるログ削除設定に今後変更予定
    out = set_log_tmpfile(namespace, log_age, PV_ROOT, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "set_log_tmpfile") )

    # k8s pvを作成しネームスペースに紐づけます。（予約容量を指定しない場合は5Giとなります。）
    out = kubectl_create_namespace_pv(namespace, pvsize, PV_ROOT, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "create_pv") )

    # ネームスペースの操作権限を持つk8s roleを作成します。
    out = kubectl_create_namespace_role(namespace, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "create_role" ) )

    # 作成したroleを契約者・全体管理者に付与（k8s rolebindingを作成）します。
    out = kubectl_get_admin_users(MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "search_admin_users" ) )

    for user in out["output"]:
        out = kubectl_create_rolebinding(namespace, user, KUBECTL_HOST, HUG_SRC_ROOT)
        if out["returncode"] != 0:

            # 削除処理 > APIエラーレスポンス（FATAL）
            return append_dict( out, clean_namespace(namespace, "add_admin_user_roles" ) )

    # ネームスペースのservice account（Podのアカウント）に監視用roleを付与（k8s rolebindingを作成）します。
    out = kubectl_create_monitoring_rolebinding(namespace, KUBECTL_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "add_monitoring_role" ) )

    # API完了レスポンス(OK)
    return {"returncode":0, "namespace":namespace }


@hug.post('/delete_namespace',  requires=authentication, versions=1)
def delete_namespace(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_namespace", body)

    # ネームスペースが存在することをチェック。
    out = is_namespace_exists(namespace, KUBECTL_HOST)
    stat = "fatal"
    if out["returncode"] != 0:

        # APIエラーレスポンス（ネームスペースが存在しない:CLEAN それ以外:FATAL）
        if out["message"].find("not found") > -1:
            # コントローラDBに残った namespace を画面から消したいときに使用
            # return { "returncode":0, "namespace":namespace, "message":"Namespace does not exist." }
            stat = "clean"
        return append_dict( out, { "namespace":namespace, "step":"is_namespace_exists", "error_stat":stat })

    # 該当ネームスペースでPodが起動していないことを確認
    out = is_namespace_busy(namespace, KUBECTL_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（Podが起動中:CLEAN それ以外:FATAL）
        if out["message"] == "Pods running in namespace":
            stat = "clean"
        return append_dict( out, { "namespace":namespace, "step":"is_namespace_busy", "error_stat":stat })

    # ネームスペースのservice account（Podのアカウント）の監視用roleを解除します。
    out = kubectl_delete_monitoring_rolebinding(namespace, MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "delete_monitoring_rolebinding" ) )

    # ネームスペースに紐づいたk8s pvc / pvを削除します
    out = kubectl_delete_namespace_pv(namespace, MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "delete_pv" ) )

    # マスターサーバーの/pv/[namespace]/logsに出力されるログの自動削除設定を削除します。
    out = unset_log_tmpfile(namespace, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "unset_log_tmpfile" ) )

    # pv recyclerに任せることに（2017/9/1）

    # ネームスペースが利用するディスク領域/pv/[namespace] を削除します。
    #out = delete_pv_dir(namespace, PV_ROOT, MASTER_HOST)
    #if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
    #    return append_dict( out, clean_namespace(namespace, "delete_pv_dir" ) )

    # k8s namespaceを削除します。
    out = kubectl_delete_namespace(namespace, KUBECTL_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_namespace(namespace, "delete_namespace" ) )

    # API完了レスポンス(OK)
    return out

# エラー発生時のネームスペース削除処理
def clean_namespace(namespace, step, stat="fatal", body=None):

    # 削除処理履歴
    message = ""

    # ネームスペースのservice account（Podのアカウント）の監視用roleを解除します。
    out = kubectl_delete_monitoring_rolebinding(namespace, MASTER_HOST)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    if out["returncode"] != 0:
        message += "delete monitoring rolebinding:" + out["message"]
    else:
        message += "delete monitoring rolebinding OK:" + out["output"]

    # ネームスペースに紐づいたk8s pvc / pvを削除します
    out = kubectl_delete_namespace_pv(namespace, MASTER_HOST)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    if out["returncode"] != 0:
        message += "delete namespace pv:" + out["message"]
    else:
        message += "delete namespace pv OK:" + out["output"]

    # マスターサーバーの/pv/[namespace]/logsに出力されるログの自動削除設定を削除します。
    out = unset_log_tmpfile(namespace, MASTER_HOST, HUG_SRC_ROOT)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    if out["returncode"] != 0:
        message += "unset log tmpfile:" + out["message"]
    else:
        message += "unset log tmpfile OK:" + out["output"]

    # pv recyclerに任せることに（2017/9/1）

    # ネームスペースが利用するディスク領域/pv/[namespace] を削除します。
    # out = delete_pv_dir(namespace, PV_ROOT, MASTER_HOST)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    # if out["returncode"] != 0:
    #    message += "delete namespace pv dir:" + out["message"]
    # else:
    #    message += "delete namespace pv dir OK:" + out["output"]

    # k8s namespaceを削除します。
    out = kubectl_delete_namespace(namespace, KUBECTL_HOST)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    if out["returncode"] != 0:
        message += "delete namespace:" + out["message"]
    else:
        message += "delete namespace OK:" + out["output"]

    # APIエラーレスポンス（FATAL）
    return {"error_stat":stat, "cleaning":message, "namespace":namespace, "step":step }

#-------------------------------------
# USER
#-------------------------------------

@hug.get('/get_user',  requires=authentication, versions=1)
def get_user():

    # リクエストログ出力
    get_log("/get_user")

    # 作業用サーバのOSユーザ一覧を取得します。
    return get_work_user(WORK_HOST)

@hug.post('/create_user',  requires=authentication, versions=1)
def create_user(role: hug.types.number, body=None):

    # リクエストログ出力
    post_log("/create_user", body)

    # 英（大文字・小文字）／数8ケタのランダム文字列を生成します（処理開始時間で乱数初期化）。
    (username, password) = generate_username()
    out = is_work_user_exists(username, WORK_HOST)
    while out["returncode"] == 0:
        (username, password) = generate_username()
        out = is_work_user_exists(username, WORK_HOST)

    if out["message"] != "User does not exsists":

        # 既存のユーザの取得に失敗 > APIエラーレスポンス（FATAL）
        return append_dict( out, { "username":username, "step":"is_work_user_exists", "error_stat":"fatal" })

    stop_audit(WORK_HOST)
    stop_audit(MASTER_HOST)

    # 作業用サーバにユーザを作成（homeディレクトリ作成）します。
    out = add_work_user(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "add_work_user"))

    uid = out["uid"]

    # 作成したユーザをdockerrootグループに属させます。「sudo docker」＝「docker」エイリアスを作成します。
    out = mod_work_user(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "mod_work_user"))

    # easyrsaツールによりユーザ名をコモンネームに設定したx509証明書を発行します。
    out = create_user_auth_x509(username, MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "add_user_auth" ))

    # マスターノードで作成したx509証明書とキーを作業用サーバのユーザ/tmpディレクトにコピーします。
    out = copy_user_auth_x509(username, MASTER_HOST, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "copy_user_auth" ))

    # 作業用サーバでsshログインのためのRSAキーペアを作成します。
    out = key_gen(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "key_gen" ))

    # RSAパブリックキーをユーザディレクトリに配置。
    out = key_copy(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "key_copy" ))

    # コンテナクラスタ操作コマンド(kubectl)の設定ファイルを設置します。
    out = kube_config_x509(username, WORK_HOST, MASTER_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "kube_config" ))

    # RSAプライベートキーを記憶
    out = print_key(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "print_key" ))

    key = out["key"]

    # RSAプライベートキーを削除
    out = delete_key(username, WORK_HOST)
    if out["returncode"] != 0:

        # 削除処理 > APIエラーレスポンス（FATAL）
        return append_dict( out, clean_user(username, "delete_key" ))

    # 全体管理者にネームスペース一覧、および全ネームスペースの操作権限roleを付与します
    if role == 0 or role == 1:
        out = kubectl_create_admin_rolebinding(username, KUBECTL_HOST, HUG_SRC_ROOT)
        if out["returncode"] != 0:

            # 削除処理 > APIエラーレスポンス（FATAL）
            return append_dict( out, clean_user(username, "create_admin_role" ))

    start_audit(WORK_HOST)
    start_audit(MASTER_HOST)

    # API完了レスポンス(OK)
    return {"returncode":0, "output":{ "key":key, "username":username, "uid":uid } }

@hug.post('/delete_user',  requires=authentication, versions=1)
def delete_user(username: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_user", body)

    # 該当ユーザの存在確認
    out = is_work_user_exists(username, WORK_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（ユーザが存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"] == "User does not exsists":
            # コントローラDBに残った user を画面から消したいときに使用
            # return {"returncode":0, "username":username, "message":"User does not exist." }
            stat = "clean"
        return append_dict( out, { "username":username, "step":"is_work_user_exists", "error_stat":stat })

    # ユーザ削除リクエスト時に該当ユーザがログインしていないことをチェックします。
    out = is_work_user_login(username, WORK_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（ユーザがログイン中:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("now logged in") > -1:
            stat = "clean"
        return append_dict( out, { "username":username, "step":"is_work_user_login", "error_stat":stat })

    # 全体管理者のネームスペース一覧、および全ネームスペースの操作権限roleを解除します
    # ※※ ユーザ削除と権限削除は別に行うコントローラアプリの仕様に合わせて、ここでは権限削除を行わない
    #out = is_admin_user(username, KUBECTL_HOST)
    #if out["returncode"] != 0:
    #    if "output" in out and out["output"].find("Admin user") > -1:
    #        out = kubectl_delete_all_rolebinding(username, KUBECTL_HOST)
    #        if out["returncode"] != 0:
    #
    #            # 削除処理 > APIエラーレスポンス（FATAL）
    #            return append_dict( out, clean_user(username, "delete_key" ))

    stop_audit(WORK_HOST)

    # 作業用サーバのOSユーザを削除します。同時にhomeディレクトリも削除されます。
    out = delete_work_user(username, WORK_HOST)
    if out["returncode"] != 0:
        stat = "fatal"
        # 下記はログインチェックに含める必要あり
        #if out["message"].find("currently used by process") > -1:
        #    stat = "clean"

        # APIエラーレスポンス（FATAL）
        return append_dict( out, { "username":username, "step":"delete_work_user", "error_stat":stat })

    start_audit(WORK_HOST)

    # API完了レスポンス(OK)
    return {"returncode":0, "username":username }

def clean_user(username, step, stat="fatal"):

    # 削除処理履歴
    message = ""

    # 作業用サーバのOSユーザを削除します。同時にhomeディレクトリも削除されます。
    out = delete_work_user(username, WORK_HOST)

    # コマンド戻り値に関わりなく次処理へ ※処理結果をmessageに保持
    if out["returncode"] != 0:
        message += " delete_work_user:" + out["message"]
    else:
        message += " delete_work_user:OK" + out["output"]

    # APIエラーレスポンス（FATAL）
    return {"error_stat":stat, "cleaning":message, "username":username, "step":step }

#-------------------------------------
# RBAC
#-------------------------------------
@hug.get('/get_rbac',  requires=authentication, versions=1)
def get_rbac():

    # リクエストログ出力
    get_log("/get_rbac")

    # 権限紐付けの情報一覧を取得します。
    # namespaceに「*」を指定した場合に全ネームスペースの情報を返します。
    return kubectl_get_rolebinding("*", MASTER_HOST)

@hug.post('/insert_rbac',  requires=authentication, versions=1)
def insert_rbac(username: hug.types.text, namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/insert_rbac", body)

    # 権限を紐づけるOSユーザーが存在することを確認します。
    out = is_work_user_exists(username, WORK_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（ユーザが存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"] == "User does not exsists":
            stat = "clean"
        return append_dict( out, { "username":username, "step":"is_work_user_exists", "error_stat":stat })

    # 対象OSユーザーにネームスペース操作権限roleを紐づけます。
    out = kubectl_create_rolebinding(namespace, username, KUBECTL_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の紐付けが存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1 or out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "username":username, "namespace":namespace, "step":"create_rolebinding", "error_stat":stat })

    # OSユーザのkubectl実行設定（デフォルトで使用するネームスペースの設定）を行います。（2017/9/25 コメントアウト）
    #out = kube_config_context_namespace(username, namespace, WORK_HOST)
    #if out["returncode"] != 0:

        # APIエラーレスポンス:FATAL
        #return append_dict( out, { "username":username, "namespace":namespace, "step":"kube_config_context_namespace", "error_stat":"fatal" })

    # API完了レスポンス(OK)
    return {"returncode":0, "username":username, "namespace":namespace }

#### delete rbac rolebindings #####
@hug.post('/delete_rbac',  requires=authentication, versions=1)
def delete_rbac(username: hug.types.text, namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_rbac", body)

    if namespace == "*":

        # 対象ユーザの全ての role 紐付け設定を解除（管理ユーザ権限も含めて削除）
        # ※※　コントローラアプリ側ではユーザ削除時に無条件でこの処理を実行
        out = kubectl_delete_all_rolebinding(username, KUBECTL_HOST)
        if out["returncode"] != 0:

            # APIエラーレスポンス:FATAL
            return append_dict( out, { "username":username, "namespace":namespace, "error_stat":"fatal" })

        # API完了レスポンス(OK)
        return out

    else:

        # 対象ユーザの対象ネームスペースの role 紐付け設定を解除
        out = kubectl_delete_rolebinding(namespace, username, KUBECTL_HOST)
        if out["returncode"] != 0:

            # APIエラーレスポンス（該当の紐付けが存在しない:CLEAN それ以外:FATAL）
            stat = "fatal"
            if out["message"].find("not found") > -1:
                stat = "clean"
            return append_dict( out, { "username":username, "namespace":namespace, "error_stat":stat })

        # API完了レスポンス(OK)
        return out

@hug.get('/get_role',  requires=authentication, versions=1)
def get_role():

    # リクエストログ出力
    get_log("/get_role")

    # role 情報一覧を取得します。
    return kubectl_get_role("*", KUBECTL_HOST)

@hug.get('/get_admin_user',  requires=authentication, versions=1)
def get_admin_user():

    # リクエストログ出力
    get_log("/get_admin_user")

    # 管理ユーザ名一覧を取得します。
    return kubectl_get_admin_users(KUBECTL_HOST)

@hug.get('/get_clusterrole',  requires=authentication, versions=1)
def get_clusterrole():

    # リクエストログ出力
    get_log("/get_clusterrole")

    # clusterrole名一覧を取得します。
    return kubectl_get_clusterrole(KUBECTL_HOST)

@hug.get('/get_clusterrole_binding',  requires=authentication, versions=1)
def get_clusterrole_binding():

    # リクエストログ出力
    get_log("/get_clusterrole_binding")

    # clusterrole名一覧を取得します。
    return kubectl_get_clusterrolebinding(KUBECTL_HOST)

@hug.post('/create_namespace_role',  requires=authentication, versions=1)
def create_namespace_role(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/create_namespace_role", body)

    # ネームスペースの操作権限 role（work-user）を作成します。
    return kubectl_create_namespace_role(namespace, KUBECTL_HOST, HUG_SRC_ROOT)

@hug.post('/delete_namespace_role',  requires=authentication, versions=1)
def delete_namespace_role(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_namespace_role", body)

    # ネームスペースの操作権限 role（work-user）を削除します。
    return kubectl_delete_namespace_role(namespace, KUBECTL_HOST)

#-------------------------------------
# INGRESS
#-------------------------------------
@hug.post('/get_ingress',  requires=authentication, versions=1)
def get_ingress(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_ingress", body)

    # ネームスペース内の ingress 情報一覧を取得します。
    return kubectl_get_ingress(namespace, MASTER_HOST, HUG_SRC_ROOT, 1)

@hug.post('/get_ingress',  requires=authentication, versions=2)
def get_ingress_v2(namespace: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_ingress(v2)", body)

    # キャッシュ
    if namespace == "*":
        cache = get_cache("get_ingress_all", "60")
        if cache["returncode"] == 0:
            return cache["json"]
        data = kubectl_get_ingress(namespace, MASTER_HOST, HUG_SRC_ROOT)
        set_cache("get_ingress_all", data)
        return data

    # ネームスペース内の ingress 情報一覧を取得します。
    return kubectl_get_ingress(namespace, MASTER_HOST, HUG_SRC_ROOT)

# FQDN設定（k8s ingress）の作成（独自ドメイン公開設定）
@hug.post('/create_ingress_prod',  requires=authentication, versions=1)
def create_ingress_prod(
        namespace: hug.types.text,
        fqdn: hug.types.text,
        service: hug.types.text,
        url_path: hug.types.text="/",
        secret: hug.types.text="",
        rewrite: hug.types.text="/",
        sticky: hug.types.number=0,
        body=None):

    # リクエストログ出力
    post_log("/create_ingress_prod", body)

    # ingress を作成する対象の service が存在することを確認し、endpointのport番号を取得します。
    out = get_service_port(namespace, service, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の service が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    # FQDN設定（k8s ingress）の作成（独自ドメイン公開設定）
    out = kubectl_create_ingress(namespace, fqdn, url_path, service, str(out["port"]), rewrite, secret, MASTER_HOST, HUG_SRC_ROOT, sticky)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress がすでに存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

@hug.post('/add_ingress_secret',  requires=authentication, versions=1)
def add_ingress_secret(namespace: hug.types.text, ingress: hug.types.text, secret: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/add_ingress_secret", body)

    # ingress に追加する対象の secret が存在することを確認します。
    out = kubectl_get_tls_secret(namespace, secret, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の secret が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "secret":secret, "ingress":ingress, "namespace":namespace, "error_stat":stat })

    # FQDN設定（k8s ingress）を更新（SSL証明書を追加）します。
    out = kubectl_add_ingress_secret(namespace, ingress, secret, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress が存在しない、ingress が既に secret を持っている:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1 or out["message"].find("already has") > -1:
            stat = "clean"
        return append_dict( out, { "secret":secret, "ingress":ingress, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

# FQDN設定（k8s ingress）の作成（k5container.net 公開設定）
# rewrite のデフォルト値を"/"に設定 (2017/7/20)
@hug.post('/create_ingress_path',  requires=authentication, versions=1)
def create_ingress_path(
        namespace: hug.types.text,
        service: hug.types.text,
        rewrite: hug.types.text="/",
        sticky: hug.types.number=0,
        body=None):

    # リクエストログ出力
    post_log("/create_ingress_path", body)

    # ingress を作成する対象の service が存在することを確認し、endpointのport番号を取得します。
    out = get_service_port(namespace, service, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の service が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })
    port = str(out["port"])

    # k5container.net 公開用の引数設定
    out = get_k5container_fqdn(MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:
        return out
    fqdn = out["output"]
    url_path = "/" + service + "-" + namespace
    secret = ""

    # FQDN設定（k8s ingress）の作成（k5container.net公開設定）
    out = kubectl_create_ingress(namespace, fqdn, url_path, service, port, rewrite, secret, MASTER_HOST, HUG_SRC_ROOT, sticky, True)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress がすでに存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

# FQDN設定（k8s ingress）の作成（k5container.net 公開設定）
@hug.post('/create_ingress_hostname',  requires=authentication, versions=2)
def create_ingress_hostname(
        namespace: hug.types.text,
        service: hug.types.text,
        url_path: hug.types.text="/",
        rewrite: hug.types.text="/",
        sticky: hug.types.number=0,
        body=None):

    # リクエストログ出力
    post_log("/create_ingress_hostname(v2)", body)

    # ingress を作成する対象の service が存在することを確認し、endpointのport番号を取得します。
    out = get_service_port(namespace, service, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の service が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })
    port = str(out["port"])

    # k5container.net 公開用の引数設定
    out = get_k5container_fqdn(MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:
        return out
    fqdn = out["output"]
    fqdn =  service + "-" + namespace + "." + fqdn
    secret = CERT_SECRET_NAME

    # FQDN設定（k8s ingress）の作成（k5container.net公開設定）
    out = kubectl_create_ingress(namespace, fqdn, url_path, service, port, rewrite, secret, MASTER_HOST, HUG_SRC_ROOT, sticky, True)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress がすでに存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

# FQDN設定（k8s ingress）の作成（クラスタFQDN/公開FQDN両方を設定）
@hug.post('/create_ingress',  requires=authentication, versions=2)
def create_ingress(
        namespace: hug.types.text,
        service: hug.types.text,
        hostname: hug.types.text,
        fqdn: hug.types.text="",
        url_path: hug.types.text="/",
        rewrite: hug.types.text="/",
        cert: hug.types.text="",
        key: hug.types.text="",
        sticky: hug.types.number=0,
        body=None):

    # リクエストログ出力
    post_log("/create_ingress(v2)", body)

    ####### バリデーション ########

    # cert/key のバリデーション
    if fqdn:
        if cert == "" or key == "":

            # APIエラーレスポンス（公開FQDNは必ず証明書が必要）
            return { "returncode":1, "message":"SSL Cert/Key not provided.", "service":service, "namespace":namespace, "error_stat":"clean" }

    # hostname のバリデーション
    if hostname != namespace and hostname != service + "-" + namespace:

        # APIエラーレスポンス（hostnameが不正:CLEAN）
        return { "returncode":1, "message":"Cluster FQDN's hostname not valid.", "service":service, "namespace":namespace, "error_stat":"clean" }

    # ingress を作成する対象の service が存在することを確認し、endpointのport番号を取得します。
    out = get_service_port(namespace, service, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の service が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    port = str(out["port"])

    # k5container.net 公開用の引数設定
    out = get_k5container_fqdn(MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:
        return out
    cluster_fqdn = out["output"]
    cluster_fqdn =  hostname + "." + cluster_fqdn
    cluster_secret = CERT_SECRET_NAME

    # 同じURLが設定されたingressが無いことを確認
    out = kubectl_get_ingress(namespace, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の namespace が存在しない:CLEAN）
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"clean" })

    for igrs in out["output"]:

        if (igrs["fqdn"] == fqdn or igrs["fqdn"] == cluster_fqdn) and url_path == igrs["url_path"] and service != igrs["backend"]["serviceName"]:

            # APIエラーレスポンス（同じURLが設定されたingressが存在する:CLEAN）
            return { "returncode":1, "message":igrs["fqdn"] + igrs["url_path"] + " is already in use with service:" + igrs["backend"]["serviceName"], "service":service, "namespace":namespace, "error_stat":"clean" }

    message = ""

    # 公開FQDNを削除したい場合のために一旦該当serviceのingressを全削除
    if not fqdn:
        out = delete_ingress_all(namespace, service)
        if out["returncode"] != 0:
            return out

    ####### クラスタFQDN ########

    # クラスタFQDN設定（k8s ingress）の作成（k5container.net公開設定）
    out = kubectl_create_ingress(namespace, cluster_fqdn, url_path, service, port, rewrite, cluster_secret, MASTER_HOST, HUG_SRC_ROOT, sticky, True)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress がすでに存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":stat })

    message += out["output"]

    ####### 公開FQDN ########

    if fqdn:

        # 証明書の存在確認をします。
        valid_secret = False
        out = kubectl_get_tls_secret(namespace, fqdn, MASTER_HOST)
        if out["returncode"] == 0:

            if out["output"]["cert"] == cert and out["output"]["key"] == key:

                # 証明書に変更がない場合
                valid_secret = True

            else:

                # 異なる証明書が存在する場合は一旦削除します。
                out = kubectl_delete_tls_secret(namespace, fqdn, MASTER_HOST)
                if out["returncode"] != 0:

                    # APIエラーレスポンス（FATAL）
                    return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"fatal" })

                message += out["output"]

        if not valid_secret:

            # SSL証明書／キーを k8s secret に登録します。
            out = kubectl_create_tls_secret(namespace, cert, key, fqdn, MASTER_HOST, HUG_SRC_ROOT)
            if out["returncode"] != 0:

                # APIエラーレスポンス（FATAL）
                return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"fatal" })

            message += out["output"]

        # FQDN設定（k8s ingress）の作成（独自ドメイン公開設定）
        out = kubectl_create_ingress(namespace, fqdn, url_path, service, port, rewrite, fqdn, MASTER_HOST, HUG_SRC_ROOT, sticky)
        if out["returncode"] != 0:

            # APIエラーレスポンス（該当の ingress がすでに存在する:CLEAN それ以外:FATAL）
            return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"fatal" })

        message += out["output"]

    clear_cache("get_ingress_all")
    # API完了レスポンス(OK)
    return {"returncode":0, "service":service, "namespace":namespace, "output":message }

@hug.post('/delete_ingress',  requires=authentication, versions=1)
def delete_ingress(namespace: hug.types.text, fqdn: hug.types.text="", service: hug.types.text="", ingress: hug.types.text="", body=None):

    # リクエストログ出力
    post_log("/delete_ingress", body)

    if not ingress:
        ingress = service + "-" + fqdn

    # 対象のFQDN設定（k8s ingress）を削除します。
    out = kubectl_delete_ingress(namespace, ingress, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の ingress が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "ingress":ingress, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

# FQDN設定（クラスタFQDN/公開FQDN両方）の ingress、secret をすべて削除
@hug.post('/delete_ingress_all',  requires=authentication, versions=2)
def delete_ingress_all(namespace: hug.types.text, service: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_ingress(v2)", body)

    out = kubectl_get_ingress(namespace, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の namespace が存在しない:CLEAN）
        return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"clean" })

    message = ""
    secret_to_delete = ""
    secrets_not_to_delete = []
    for igrs in out["output"]:

        if igrs["backend"]["serviceName"] == service:

            # 対象のFQDN設定（k8s ingress）を削除します。
            delout = kubectl_delete_ingress(namespace, igrs["name"], MASTER_HOST)
            if delout["returncode"] != 0:

                # APIエラーレスポンス（FATAL）
                return append_dict( delout, { "service":service, "namespace":namespace, "error_stat":"fatal" })

            message += delout["output"]

            # 1つの公開FQDNで複数のserviceを参照している場合もあるのでここではsecretを削除しない
            if igrs["type"] == "custom":
                secret_to_delete = igrs["secret"]

        else:
            if igrs["type"] == "custom":
                secrets_not_to_delete.append(igrs["secret"])

    if secret_to_delete and not secret_to_delete in secrets_not_to_delete:

        # SSL証明書／キーが登録された k8s secret を削除します。
        out = kubectl_delete_tls_secret(namespace, secret_to_delete, MASTER_HOST)
        if out["returncode"] != 0:

            # APIエラーレスポンス（FATAL）
            return append_dict( out, { "service":service, "namespace":namespace, "error_stat":"fatal" })

        message += out["output"]
        clear_cache("get_secret_" + namespace + "_" + secret_to_delete)

    if not message:
        message = "No ingresses exists"

    clear_cache("get_ingress_all")

    # API完了レスポンス(OK)
    return {"returncode":0, "output":message }

#-------------------------------------
# CLUSTER FQDN
#-------------------------------------
@hug.get('/get_default_fqdn',  requires=authentication, versions=1)
def get_default_fqdn():

    # リクエストログ出力
    get_log("/get_default_fqdn")

    # クラスタFQDN [クラスタ固有の文字列].k5container.net を取得します。
    return get_k5container_fqdn(MASTER_HOST, HUG_SRC_ROOT)

@hug.post('/set_default_fqdn',  requires=authentication, versions=1)
def set_default_fqdn(fqdn: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/set_default_fqdn", body)

    # クラスタFQDN [クラスタ固有の文字列].k5container.net を設定します。
    out = set_k5container_fqdn(fqdn, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス
        return out

    # API完了レスポンス(OK)
    return { "returncode":0, "fqdn":fqdn }

@hug.post('/gen_cluster_fqdn',  requires=authentication, versions=1)
def gen_cluster_fqdn(cluster_id: hug.types.text, region: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/gen_cluster_fqdn", body)

    # クラスタFQDN [クラスタ固有の文字列].k5container.net を生成します。
    return { "returncode":0, "fqdn":generate_cluster_fqdn(cluster_id, region) }

@hug.post('/create_cluster_fqdn',  requires=authentication, versions=1)
def create_cluster_fqdn(fqdn: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/create_cluster_fqdn", body)

    # クラスタFQDNの証明書を発行します
    out = create_cluster_cert(fqdn, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス
        return out

    # 新しい証明書で nginx-ingress を再起動させます
    out = update_ingress_cert(fqdn, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス
        return out

    # hug-apiにクラスタFQDNを保持
    out = set_k5container_fqdn(fqdn, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス
        return out

    # API完了レスポンス(OK)
    return { "returncode":0, "output":{"fqdn":fqdn, "cacert":print_cacert(MASTER_HOST)["output"] }}

@hug.get('/get_cacert',  requires=authentication, versions=1)
def get_cacert():

    # リクエストログ出力
    get_log("/get_cacert")

    # クラスタFQDN [クラスタ固有の文字列].k5container.net を取得します。
    return print_cacert(MASTER_HOST)

@hug.get('/get_resolve_status',  requires=authentication, versions=1)
def get_resolve_status():

    # リクエストログ出力
    get_log("/get_resolve_status")

    # クラスタFQDNのDNS解決結果を取得します。
    out = get_k5container_fqdn(MASTER_HOST, HUG_SRC_ROOT)
    return resolve_cluster_fqdn(out["output"], MASTER_HOST)

#-------------------------------------
# SECRET
#-------------------------------------
@hug.post('/create_secret',  requires=authentication, versions=1)
def create_secret(namespace: hug.types.text, fqdn: hug.types.text, cert: hug.types.text, key: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/create_secret", body)

    # SSL証明書／キーを k8s secret に登録します。
    out = kubectl_create_tls_secret(namespace, cert, key, fqdn, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（namespaceが存在しない、該当の secret が既に存在する:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1 or out["message"].find("already exists") > -1:
            stat = "clean"
        return append_dict( out, { "secret":fqdn, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

@hug.post('/update_secret',  requires=authentication, versions=1)
def update_secret(namespace: hug.types.text, fqdn: hug.types.text, cert: hug.types.text, key: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/update_secret", body)

    # k8s secret に登録されているSSL証明書／キーを更新します。
    out = kubectl_update_tls_secret(namespace, cert, key, fqdn, MASTER_HOST, HUG_SRC_ROOT)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の secret が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "secret":fqdn, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

@hug.post('/delete_secret',  requires=authentication, versions=1)
def delete_secret(namespace: hug.types.text, secret: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/delete_secret", body)

    # SSL証明書／キーが登録された k8s secret を削除します。
    out = kubectl_delete_tls_secret(namespace, secret, MASTER_HOST)
    if out["returncode"] != 0:

        # APIエラーレスポンス（該当の secret が存在しない:CLEAN それ以外:FATAL）
        stat = "fatal"
        if out["message"].find("not found") > -1:
            stat = "clean"
        return append_dict( out, { "secret":secret, "namespace":namespace, "error_stat":stat })

    # API完了レスポンス(OK)
    return out

@hug.post('/get_secret',  requires=authentication, versions=1)
def get_secret(namespace: hug.types.text, secret: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/get_seceret", body)

    # キャッシュ
    cache = get_cache("get_secret_" + namespace + "_" + secret, "1440")
    if cache["returncode"] == 0:
        return cache["json"]
    data = kubectl_get_tls_secret(namespace, secret, MASTER_HOST)
    set_cache("get_secret_" + namespace + "_" + secret, data)
    return data

    # k8s secret に登録されているSSL証明書／キーの中身を表示します。
    #return kubectl_get_tls_secret(namespace, secret, MASTER_HOST)


@hug.post('/logging_test',  requires=authentication, versions=1)
def logging_test(message: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/logging_test", body)

    return { "message":message }

#-------------------------------------
# ADMIN JOBS
#-------------------------------------

@hug.get('/restore_secrets',  requires=authentication, versions=1)
def restore_secrets():

    # リクエストログ出力
    get_log("/restore_secrets")

    return kubectl_restore_secrets(MASTER_HOST)

@hug.get('/delete_unused_pvc',  requires=authentication, versions=1)
def delete_unused_pvc():

    # リクエストログ出力
    get_log("/delete_unused_pvc")

    return kubectl_delete_unused_pvc(MASTER_HOST)

#-------------------------------------
# ADMIN COMMANDS
#-------------------------------------

@hug.post('/work_log_tail',  requires=authentication, versions=1)
def work_log_tail(path: hug.types.text, lines: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/work_log_tail", body)

    # スクリプティング対策
    if not path_chk(path) or not num_chk(lines):
        return {"returncode":1, "message":"Invalid parameters"}

    return tail_log(path, lines, WORK_HOST)

@hug.post('/master_log_tail',  requires=authentication, versions=1)
def master_log_tail(path: hug.types.text, lines: hug.types.text, body=None):

    # リクエストログ出力
    post_log("/master_log_tail", body)

    # スクリプティング対策
    if not path_chk(path) or not num_chk(lines):
        return {"returncode":1, "message":"Invalid parameters"}

    return tail_log(path, lines, MASTER_HOST)

@hug.post('/work_command',  requires=authentication, versions=1)
def work_command(cmd: hug.types.text, timer: hug.types.number=10, body=None):

    # リクエストログ出力
    post_log("/work_command", body)

    # &&、||、パイプとリダイレクトは禁止
    if not cmd_chk(cmd):
        return {"returncode":1, "message":"Invalid parameters"}

    return do_cmd(cmd, WORK_HOST, timer)

@hug.post('/master_command',  requires=authentication, versions=1)
def master_command(cmd: hug.types.text, timer: hug.types.number=10, body=None):

    # リクエストログ出力
    post_log("/master_command", body)

    # &&、||、パイプとリダイレクトは禁止
    if not cmd_chk(cmd):
        return {"returncode":1, "message":"Invalid parameters"}

    return do_cmd(cmd, MASTER_HOST, timer)

@hug.get('/work_kill_playbook',  requires=authentication, versions=1)
def work_kill_playbook():

    # リクエストログ出力
    get_log("/kill_playbook")

    return kill_playbook(WORK_HOST)

@hug.get('/work_chk_reboot',  requires=authentication, versions=1)
def work_chk_reboot():

    # リクエストログ出力
    get_log("/work_chk_reboot")

    return chk_reboot(WORK_HOST)

#-------------------------------------
# MAINTENANCE
#-------------------------------------

@hug.post('/do_maintenance',  requires=authentication, versions=1)
def do_maintenance_v1(maintenance_id: hug.types.text, yamls: hug.types.text="", redo: hug.types.number=0, body=None):

    # リクエストログ出力
    post_log("/do_maintenance", body)

    return maintenance_playbook_v1(maintenance_id, yamls, WORK_HOST, redo)

@hug.get('/get_maintenance/{maintenance_id}', requires=authentication, versions=1)
def get_maintenance_v1(maintenance_id: hug.types.text):

    # リクエストログ出力
    get_log("/get_maintenance/" + maintenance_id)

    return get_maintenance_result_v1(maintenance_id, WORK_HOST)

@hug.get('/get_maintenance',  requires=authentication, versions=1)
def get_maintenance_v1():

    # リクエストログ出力
    get_log("/get_maintenance")

    return get_maintenance_list_v1(WORK_HOST)

@hug.get('/ansible_log_tail',  requires=authentication, versions=1)
def ansible_log_tail(lines="10"):

    # リクエストログ出力
    get_log("/ansible_log_tail")

    # スクリプティング対策
    if not num_chk(lines):
        return {"returncode":1, "message":"Invalid parameters"}

    return tail_log("/home/k5user/playbooks/ansible.log", lines, WORK_HOST)

#-------------------------------------
# MAINTENANCE V2
#-------------------------------------

@hug.post('/do_maintenance',  requires=authentication, versions=2)
def do_maintenance(maintenance_id: hug.types.text, yamls: hug.types.text="", work_reboot: hug.types.number=0, redo: hug.types.number=0, body=None):

    # リクエストログ出力
    post_log("/do_maintenance", body)

    return maintenance_playbook(maintenance_id, yamls, WORK_HOST, work_reboot, redo)

@hug.get('/get_maintenance/{maintenance_id}', requires=authentication, versions=2)
def get_maintenance(maintenance_id: hug.types.text):

    # リクエストログ出力
    get_log("/get_maintenance/" + maintenance_id)

    return get_maintenance_result(maintenance_id, WORK_HOST)

@hug.get('/get_maintenance',  requires=authentication, versions=2)
def get_maintenance():

    # リクエストログ出力
    get_log("/get_maintenance")

    return get_maintenance_list(WORK_HOST)


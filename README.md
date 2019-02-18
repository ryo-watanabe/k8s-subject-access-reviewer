# k8s-subject-access-reviewer

### TLS secret
````
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -days 100000 -out ca.crt -subj "/CN=subject-access-reviewer-ca"

cat >server.conf <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name
[req_distinguished_name]
[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, serverAuth
EOF

openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=localhost" -config server.conf
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 100000 -extensions v3_req -extfile server.conf

kubectl create secret tls nginx-tls --cert=server.crt --key=server.key
````

### Configmap for apiserver.py
````
kubectl create cm apiserver-pi --from-file apiserver.py
````

### Deploy reviewer on master as a pod
````
kubectl apply -f deploy.yaml
````

### Copy reviewer-config.yaml and cacert on master
````
/etc/kubernetes/review/ca.crt
/etc/kubernetes/review/reviewer-config.yaml
````

### Add options and restart kube-apiserver
````
--authorization-mode: "Node,RBAC,Webhook"
--authorization-webhook-config-file: "/etc/kubernetes/review/reviewer-config.yaml"
--runtime-config: "authorization.k8s.io/v1beta1=true"
````

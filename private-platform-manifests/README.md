# Private Platform Source Manifests

These files preserve the working private portal, oauth2-proxy, ingress buffer settings, TLS routing and NetworkPolicies.

The Secret `platform-oauth2-proxy` is intentionally excluded from Git. It must contain:

- `client-secret`
- `cookie-secret`

Apply with:

```bash
kubectl apply -f private-platform-manifests/
```

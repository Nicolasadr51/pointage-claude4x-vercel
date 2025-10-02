import os
import anthropic
import sys

print("Starting Claude 4.X CSP v2 correction script...", file=sys.stderr)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

try:
    with open("src/main.py", "r") as f:
        code_to_review = f.read()
    print("Successfully read src/main.py", file=sys.stderr)
except FileNotFoundError:
    print("Error: src/main.py not found.", file=sys.stderr)
    sys.exit(1)

console_errors = """
Refused to connect to https://plausible.io/api/event because it does not appear in the connect-src directive of the Content Security Policy.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: the server responded with a status of 404 ()
"""

print("Calling Claude API for CSP v2 correction...", file=sys.stderr)
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4000,
    messages=[{
        "role": "user", 
        "content": f"""J'ai une application Flask et je rencontre des erreurs de Content Security Policy (CSP) dans la console du navigateur. La ligne de CSP actuelle a déjà été mise à jour une fois, mais une nouvelle erreur persiste pour `plausible.io`. Voici les erreurs exactes de la console :\n\n```\n{console_errors}\n```\n\nVoici la ligne actuelle de la CSP dans mon code Python Flask (src/main.py) :\n\n```python\nresponse.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://plausible.io 'unsafe-inline' 'unsafe-eval'; style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline'; img-src 'self' data: https://* blob:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' https://api.manus.im https://api2.amplitude.com https://sr-client-cfg.amplitude.com; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';"\n```\n\nLe problème est que `plausible.io/api/event` est toujours bloqué par `connect-src`.\n\nVeuillez me fournir la ligne **complète et corrigée** de la Content Security Policy qui résout toutes les erreurs listées ci-dessus, en particulier celle de `plausible.io/api/event`. La CSP doit être sécurisée mais permettre le bon fonctionnement de l'application. Assurez-vous que la syntaxe est correcte pour Flask.\n\nFournissez uniquement la ligne corrigée de la CSP, sans explication supplémentaire, pour que je puisse la remplacer directement dans le code.\n"""
    }]
)

print("Claude API call for CSP v2 correction finished.", file=sys.stderr)
print(response.content[0].text)


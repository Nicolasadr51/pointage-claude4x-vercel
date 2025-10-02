import os
import anthropic
import sys

print("Starting Claude 4.X analysis script...", file=sys.stderr)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

try:
    with open("src/main.py", "r") as f:
        code_to_review = f.read()
    print("Successfully read src/main.py", file=sys.stderr)
except FileNotFoundError:
    print("Error: src/main.py not found.", file=sys.stderr)
    sys.exit(1)

print("Calling Claude API...", file=sys.stderr)
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4000, # Increased max_tokens
    messages=[{
        "role": "user", 
        "content": f"""L'utilisateur rencontre une erreur 404 lorsqu'il clique sur un bouton dans l'application déployée. Cela indique un problème de routage ou de soumission de formulaire.\n\nVoici le code Python Flask actuel (src/main.py) :\n\n```python\n{code_to_review}\n```\n\nVeuillez analyser le code et identifier la cause probable de l'erreur 404. Concentrez-vous sur :\n1. Les routes définies (`@app.route`).\n2. Les actions des formulaires (`<form action=\"...">`).\n3. La génération des URLs (`url_for`).\n4. Toute autre configuration qui pourrait affecter le routage ou la gestion des requêtes.\n\nExpliquez la cause du problème et proposez une solution concrète pour le corriger. Fournissez le code corrigé si nécessaire.\n"""
    }]
)

print("Claude API call finished.", file=sys.stderr)
print("=== ANALYSE CLAUDE 4.X POUR ERREUR 404 ===")
print(response.content[0].text)


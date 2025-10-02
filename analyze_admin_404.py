import os
import anthropic
import sys

print("Starting Claude 4.X analysis script for Admin 404...", file=sys.stderr)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

try:
    with open("src/main.py", "r") as f:
        code_to_review = f.read()
    print("Successfully read src/main.py", file=sys.stderr)
except FileNotFoundError:
    print("Error: src/main.py not found.", file=sys.stderr)
    sys.exit(1)

print("Calling Claude API for Admin 404 analysis...", file=sys.stderr)
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4000,
    messages=[{
        "role": "user", 
        "content": f"""L'utilisateur rencontre une erreur 404 lorsqu'il clique sur le bouton 'Administration' depuis le tableau de bord employé. Cela indique un problème de routage ou d'accès à la route '/admin'.\n\nVoici le code Python Flask actuel (src/main.py) :\n\n```python\n{code_to_review}\n```\n\nVeuillez analyser le code et identifier la cause probable de l'erreur 404 pour la route '/admin'. Concentrez-vous sur :\n1. La définition de la route `@app.route('/admin')` et sa fonction associée (`admin_dashboard`).\n2. Le décorateur `@admin_required` et sa logique d'authentification/autorisation.\n3. Les liens ou formulaires qui mènent à cette route dans les templates HTML.\n4. Toute autre configuration qui pourrait affecter le routage ou la gestion des requêtes pour cette route.\n\nExpliquez la cause du problème et proposez une solution concrète pour le corriger. Fournissez le code corrigé si nécessaire.\n"""
    }]
)

print("Claude API call for Admin 404 analysis finished.", file=sys.stderr)
print("=== ANALYSE CLAUDE 4.X POUR ERREUR 404 ADMIN ===")
print(response.content[0].text)


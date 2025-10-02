import os
import anthropic
import sys

print("Starting Claude 4.X analysis script for Admin Dashboard error...", file=sys.stderr)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

try:
    with open("src/main.py", "r") as f:
        code_to_review = f.read()
    print("Successfully read src/main.py", file=sys.stderr)
except FileNotFoundError:
    print("Error: src/main.py not found.", file=sys.stderr)
    sys.exit(1)

print("Calling Claude API for Admin Dashboard error analysis...", file=sys.stderr)
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4000,
    messages=[{
        "role": "user", 
        "content": f"""L'utilisateur rencontre une erreur "Erreur lors du chargement du tableau de bord administrateur" après avoir cliqué sur le bouton 'Administration'. Cela indique un problème dans la fonction `admin_dashboard` ou dans le rendu de son template `ADMIN_DASHBOARD_TEMPLATE`.\n\nVoici le code Python Flask actuel (src/main.py) :\n\n```python\n{code_to_review}\n```\n\nVeuillez analyser la fonction `admin_dashboard` et le `ADMIN_DASHBOARD_TEMPLATE` pour identifier la cause probable de cette erreur. Concentrez-vous sur :\n1. Les variables passées au template et leur disponibilité.\n2. Les boucles ou conditions dans le template qui pourraient causer des erreurs si les données sont manquantes ou mal formatées.\n3. Les appels de fonctions ou de méthodes dans `admin_dashboard` qui pourraient échouer (ex: requêtes DB, calculs de stats).\n4. Toute autre incohérence entre la logique Python et le rendu HTML.\n\nExpliquez la cause du problème et proposez une solution concrète pour le corriger. Fournissez le code corrigé si nécessaire.\n"""
    }]
)

print("Claude API call for Admin Dashboard error analysis finished.", file=sys.stderr)
print("=== ANALYSE CLAUDE 4.X POUR ERREUR TABLEAU DE BORD ADMIN ===")
print(response.content[0].text)


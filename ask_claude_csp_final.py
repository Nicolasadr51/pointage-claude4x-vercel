'''
Script pour demander à Claude 4.X de fournir une directive Content Security Policy (CSP) finale et complète.
'''
import os
import anthropic

# Récupérer le code source complet
try:
    with open("/home/ubuntu/pointage-claude4x/src/main.py", "r") as f:
        source_code = f.read()
except FileNotFoundError:
    print("Erreur: Le fichier src/main.py n'a pas été trouvé.")
    exit()

# Erreurs de la console
console_errors = """
Refused to connect to https://plausible.io/api/event because it does not appear in the connect-src directive of the Content Security Policy.
Failed to load resource: Vous n'avez pas l'autorisation d'accéder à la ressource requise.
Failed to load resource: the server responded with a status of 404 () for https://cdn.jsdelivr.net/npm/chart.umd.min.js.map
Refused to load data:image/svg+xml,... because it appears in neither the img-src directive nor the default-src directive of the Content Security Policy.
Refused to connect to https://api.manus.im/space.v1.SpaceService/HasSpaceEditPermission because it does not appear in the connect-src directive of the Content Security Policy.
Refused to connect to https://plausible.io/js/script.file-downloads.hash.outbound-links.pageview-props.revenue.tagged-events.js because it does not appear in the script-src directive of the Content Security Policy.
Refused to connect to https://api.manus.im/api/user_behavior/batch_create_event_v2 because it does not appear in the connect-src directive of the Content Security Policy.
Refused to connect to https://sr-client-cfg.amplitude.com/config/46ac3f9abb41dd2d17a5785e052bc6d3?config_group=browser because it does not appear in the connect-src directive of the Content Security Policy.
"""

# Prompt pour Claude 4.X
prompt = f"""
Bonjour Claude 4.X,

L'application Flask suivante rencontre des erreurs persistantes de Content Security Policy (CSP) qui empêchent le tableau de bord administrateur de se charger correctement. Voici le code source complet de `src/main.py` et les erreurs exactes de la console du navigateur.

**Objectif :** Fournir une seule et unique chaîne de caractères pour la directive `Content-Security-Policy` qui résoudra **toutes** les erreurs de la console et permettra à l'application de fonctionner correctement. La chaîne doit être directement insérable dans le code Python.

**Code source (`src/main.py`) :**
```python
{source_code}
```

**Erreurs de la console :**
```
{console_errors}
```

**Instructions :**
1. Analyse attentivement toutes les erreurs de la console pour identifier chaque source bloquée (scripts, connexions, images, etc.).
2. Examine la directive CSP actuelle dans le code source.
3. Construis une nouvelle directive CSP complète qui autorise toutes les sources nécessaires (`plausible.io`, `cdn.jsdelivr.net`, `api.manus.im`, `amplitude.com`, les images SVG `data:`, etc.).
4. Assure-toi que la syntaxe de la chaîne est correcte pour être utilisée dans le code Python (échappement des apostrophes si nécessaire).
5. Ne fournis que la chaîne de la directive CSP, rien d'autre.

**Exemple de format de réponse attendu :**
`"default-src 'self'; script-src 'self' https://example.com; ..."`
"""

# Appel à l'API Anthropic
try:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extraire et sauvegarder la réponse
    csp_correction = message.content[0].text
    with open("/home/ubuntu/pointage-claude4x/claude4x_csp_final_correction.txt", "w") as f:
        f.write(csp_correction)
    
    print("Correction de la CSP générée par Claude 4.X et sauvegardée dans claude4x_csp_final_correction.txt")

except Exception as e:
    print(f"Une erreur est survenue lors de l'appel à l'API Claude 4.X: {e}")


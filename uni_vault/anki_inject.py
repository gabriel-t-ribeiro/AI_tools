import os
import json
import urllib.request
import glob

def anki_request(action, **params):
    payload = json.dumps({'action': action, 'version': 6, 'params': params}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8765', data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode('utf-8'))
        return res

deck_map = {
    '2m1s_ma': 'MA',
    '2m1s_ppfm': 'PPFM',
    '2m1s_SAVI': 'SAVI',
    '2m1s_adpe': 'ADPE',
    '2m_dissertation': 'DPE',
    '2m_dissertation': 'DPE',
    'learning_uni': 'Learning'
}

# Criar baralhos se não existirem
res_decks = anki_request('deckNames')
existing_decks = set(res_decks.get('result', []))
for target_deck in set(deck_map.values()):
    if target_deck not in existing_decks:
        anki_request('createDeck', deck=target_deck)
        print(f"Baralho criado: {target_deck}")

files = glob.glob('./**/*_fc.txt', recursive=True)

total_added = 0
total_duplicates = 0
deck_stats = {}

for fpath in sorted(files):
    parts = fpath.strip('./').split('/')
    top_dir = parts[0]
    filename = parts[-1]
    
    # Specific deck routing
    if 'ctf2' in filename.lower():
        deck_name = 'ctf2'
    else:
        deck_name = deck_map.get(top_dir, 'Default')
    tag = parts[-1].replace('.txt', '')
    
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line or ';' not in line:
            continue
        
        parts_line = line.split(';', 1)
        front = parts_line[0].strip()
        back = parts_line[1].strip()
        
        note = {
            'deckName': deck_name,
            'modelName': 'Basic',
            'fields': {
                'Front': front,
                'Back': back
            },
            'tags': [deck_name.lower(), tag],
            'options': {
                'allowDuplicate': False,
                'duplicateScope': 'deck'
            }
        }
        
        res = anki_request('addNote', note=note)
        if deck_name not in deck_stats:
            deck_stats[deck_name] = {'added': 0, 'duplicates': 0}
            
        if res.get('error') is None and res.get('result'):
            total_added += 1
            deck_stats[deck_name]['added'] += 1
        else:
            total_duplicates += 1
            deck_stats[deck_name]['duplicates'] += 1

print("\n--- RESUMO DA IMPORTAÇÃO ---")
print(f"Cartões novos inseridos: {total_added}")
print(f"Duplicados / já existentes ignorados: {total_duplicates}")
print("\nPor baralho:")
for d, s in sorted(deck_stats.items()):
    print(f"- {d}: {s['added']} novos inseridos | {s['duplicates']} já existiam no Anki")

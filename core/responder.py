_INDEX_BY_INTENT = {}


def respond(nlu, intent_name, lang):
    if intent_name is None:
        return ("No entendi tu solicitud, ¿puedes reformularla?" if lang == "es"
                else "I didn't understand that, could you rephrase?")
    idx = _INDEX_BY_INTENT.get(intent_name, 0)
    _INDEX_BY_INTENT[intent_name] = idx + 1
    return nlu.response_for(intent_name, lang, idx) or (
        "No tengo una respuesta para eso todavia." if lang == "es"
        else "I don't have a response for that yet."
    )

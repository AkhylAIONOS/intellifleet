"""Language normalization only. All identifiers/facts are resolved by repositories."""
import asyncio
import json
import re
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

INTENTS=('SERVICE_SEARCH','SERVICE_DETAILS','FLIGHT_DETAILS','RUN_DETAILS','RESOURCE_LOOKUP',
    'CAPACITY_LOOKUP','SCHEDULE_LOOKUP','COMPARE_SERVICES','PLAN_SHIPMENT','CHANGE_SHIPMENT_WEIGHT',
    'DELAY_SCENARIO','BREAKDOWN_SCENARIO','BLOCK_SERVICE','RECOVERY','COST_COMPARISON',
    'RISK_COMPARISON','VOLUME_LOOKUP','NETWORK_LOOKUP','FOLLOW_UP_REFERENCE')


class NormalizedIntent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    intent: Literal[INTENTS]='FOLLOW_UP_REFERENCE'
    origin: str|None=None
    destination: str|None=None
    identifier: str|None=None
    mode: Literal['AIR','SURFACE','RAIL']|None=None
    weight_kg: float|None=Field(default=None,gt=0,allow_inf_nan=False)
    delay_minutes: float|None=Field(default=None,gt=0,le=1440,allow_inf_nan=False)
    language: Literal['en','hi','hinglish']='en'


def classify(message):
    t=message.casefold()
    translated=t.replace('से',' se ').replace('के लिए',' ke liye ').replace('का',' ka ').replace('की',' ki ')
    modes=[m for m,pattern in [('AIR',r'\bair\b|हवाई'),('SURFACE',r'\bsurface\b|सड़क|gaadi|गाड़ी'),('RAIL',r'\btrain\b|\brail\b|ट्रेन')] if re.search(pattern,t)]
    mode=modes[0] if len(modes)==1 else None
    weight=re.search(r'([\d,]+(?:\.\d+)?)\s*(?:kg\b|kilograms?\b|किलो)',t)
    delay=re.search(r'(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?\b|मिनट)',t)
    if re.search(r'break(?:s|ing)?\s*down|broke(?:n)?\s*down|breakdown|ho gayi|kharab|खराब|ब्रेकडाउन',t):intent='BREAKDOWN_SCENARIO'
    elif 'delay' in t or 'देरी' in t:intent='DELAY_SCENARIO'
    elif re.search(r'unavailable|blocked|block\b|बंद|उपलब्ध नहीं',t):intent='BLOCK_SERVICE'
    elif weight and re.search(r'becomes?|increase|change|instead|make it|now|अब|badha|badal|ho ja|हो जाए|कर दो|happens if',t):intent='CHANGE_SHIPMENT_WEIGHT'
    elif re.search(r'\bplan\b|योजना|planning|shipment.*(?:book|send)',t):intent='PLAN_SHIPMENT'
    elif re.search(r'cheapest|cost|price|fuel|सस्ता|कीमत|sasta',t):intent='COST_COMPARISON'
    elif re.search(r'risk|reliab|जोखिम',t):intent='RISK_COMPARISON'
    elif re.search(r'breakdown.*recover|replacement|replace|recover|बदल|replacement batao',t):intent='RECOVERY'
    elif re.search(r'capacity|utilization|carry|feasib|calculation|क्षमता|wazan|weight.*limit',t):intent='CAPACITY_LOOKUP'
    elif re.search(r'vehicle|resource|assigned|gaadi|गाड़ी',t):intent='RESOURCE_LOOKUP'
    elif re.search(r'shipments|volume|packages|affected|मात्रा',t):intent='VOLUME_LOOKUP'
    elif re.search(r'arrives? first|faster|fastest|compare|\bvs\b|versus|पहले|जल्दी|jaldi',t):intent='COMPARE_SERVICES'
    elif re.search(r'\beta\b|\betd\b|schedule|handover|cutoff|departure|arrival|समय',t):intent='SCHEDULE_LOOKUP'
    elif re.search(r'services?.*(?:available|exist)|available.*services?|kya services|कौन.*services|सेवाएं|सेवाएँ',t):intent='SERVICE_SEARCH'
    elif re.search(r'\brun\b',t):intent='RUN_DETAILS'
    elif mode or re.search(r'option|flight|service|विकल्प|उड़ान',t):intent='SERVICE_DETAILS'
    elif re.search(r'network|stations|gateways|नेटवर्क',t):intent='NETWORK_LOOKUP'
    else:intent='FOLLOW_UP_REFERENCE'
    pair=re.search(r'\bfrom\s+(.+?)\s+to\s+(.+?)(?:[?.!]|$)',message,re.I)
    if not pair:pair=re.search(r'([A-Z0-9]+)\s+(?:se|से)\s+([A-Z0-9]+)\s+(?:ke liye|के लिए)',translated,re.I)
    if pair:
        origin=pair[1].strip();destination=re.split(r'\s+(?:is|are|which|with|for|cheapest|fastest|by|via|using|weighing)\b',pair[2],maxsplit=1,flags=re.I)[0].strip()
    else:origin=destination=None
    return NormalizedIntent(intent=intent,origin=origin,destination=destination,mode=mode,
        weight_kg=float(weight[1].replace(',','')) if weight else None,
        delay_minutes=float(delay[1]) if delay else None,
        language='hi' if re.search('[\u0900-\u097f]',message) else 'hinglish' if re.search(r'\b(se|kya|hai|ka|ki|gaadi|batao)\b',t) else 'en')


@lru_cache(maxsize=1)
def language_model():
    from backend.llm.provider import create_chat_model, provider_status
    return create_chat_model() if provider_status().configured else None


async def normalize(message):
    fallback=classify(message)
    try:model=language_model()
    except Exception:return fallback,'offline-normalization'
    if model is None:return fallback,'offline-normalization'
    prompt=('Normalize English, Hindi or Hinglish into the JSON schema below. This is intent extraction only. '
        'Never answer, invent facts, infer station names or choose an entity from UI selection. '
        'Extract only entities literally mentioned; null for missing fields. Preserve identifiers. '
        'Return JSON only. Intents: '+', '.join(INTENTS)+'. Fields: intent, origin, destination, identifier, mode '
        '(AIR/SURFACE/RAIL/null), weight_kg, delay_minutes, language (en/hi/hinglish).')
    try:
        result=await asyncio.wait_for(model.ainvoke([('system',prompt),('human',message)]),timeout=12)
        content=result.content
        if isinstance(content,list):content=''.join(x.get('text','') for x in content if isinstance(x,dict))
        data=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',str(content).strip()))
        normalized=NormalizedIntent(**data)
        # Discard extracted entities unless they are literally present in this turn.
        literal=lambda value: value and re.sub(r'\s+','',value.casefold()) in re.sub(r'\s+','',message.casefold())
        if not literal(normalized.identifier):normalized.identifier=None
        if not literal(normalized.origin):normalized.origin=None
        if not literal(normalized.destination):normalized.destination=None
        # Numeric parameters explicitly in the message always outrank model parsing.
        normalized.weight_kg=fallback.weight_kg
        normalized.delay_minutes=fallback.delay_minutes
        normalized.mode=fallback.mode
        if fallback.origin and fallback.destination:normalized.origin=fallback.origin;normalized.destination=fallback.destination
        if fallback.intent in {'PLAN_SHIPMENT','CHANGE_SHIPMENT_WEIGHT','BREAKDOWN_SCENARIO','DELAY_SCENARIO','BLOCK_SERVICE','SERVICE_SEARCH','RESOURCE_LOOKUP','CAPACITY_LOOKUP','SCHEDULE_LOOKUP','COST_COMPARISON','COMPARE_SERVICES'}:normalized.intent=fallback.intent
        return normalized,'llm-normalization'
    except Exception:
        # Facts still come from deterministic repositories, even when the model fails.
        return fallback,'offline-normalization'

// Port of vigilix/rag/query.py.
import { Dictionary } from "./dict";
import { DOSING } from "./guard";
import { analyse } from "./text";

export const INTENTS = ["method", "signal", "interaction", "label", "adverse_effect", "population", "management", "trial", "case", "mechanism", "regulation"];

const PATTERNS: Record<string, RegExp> = {
  method: /\b(prr|ror|ebgm|eb05|mgps|bcpnn|information component|proportional reporting|reporting odds|disproportionalit\w*|masking|naranjo|causality|who umc|bradford hill|self controlled|signal detection|data mining|shrinkage|duplicates?|weber effect|notoriety|time to onset|observed versus expected|reference set|meddra|smq)\b/gi,
  signal: /\b(faers|signals?|reports?|reported|reporting|spontaneous|yellow card|vigibase|eudravigilance|disproportionat\w*|stand out|data mining|pharmacovigilance)\b/gi,
  interaction: /\b(interact\w*|together|combin\w*|co ?administ\w*|concomitant|plus|with an?|and an?|taken with|alongside|cyp\w*|inhibitor|inducer|p glycoprotein)\b/gi,
  label: /\b(label\w*|boxed warning|black box|smpc|summary of product characteristics|prescribing information|warnings?|precautions?|listed|section 4\.?8|undesirable effects|contraindicat\w*)\b/gi,
  adverse_effect: /\b(cause\w*|induced?|side effects?|adverse|reactions?|toxicit\w*|risk\w*|associated|linked|known|expected|common|safety|harm\w*|problems?|issues?)\b/gi,
  population: /\b(pregnan\w*|breast ?feeding|lactation|elderly|older (adults|people|patients)|children|paediatric|pediatric|infants?|neonat\w*|renal impairment|hepatic impairment|kidney disease|under \d+|aged)\b/gi,
  management: /\b(manage\w*|monitor\w*|prevent\w*|avoid\w*|treat\w*|what to do|should|stop\w*|switch\w*|reduce\w*|mitigat\w*|screen\w*)\b/gi,
  trial: /\b(trials?|randomi[sz]ed|rct|placebo|versus|vs|tolerabilit\w*|discontinu\w*|study|studies)\b/gi,
  case: /\b(case reports?|case series|reports? of|patient (developed|presented)|my patient)\b/gi,
  mechanism: /\b(mechanism|why|how does|pathophysiolog\w*|because)\b/gi,
  regulation: /\b(ich|gvp|mhra|fda|ema|prac|regulator\w*|psur|pbrer|risk management plan|rmp|icsr|e2a|e2b|e2c|seriousness|serious criteria|expedited)\b/gi,
};

export const POP: Record<string, RegExp> = {
  pregnancy: /\b(pregnan\w*|teratogen\w*|fetal|foetal|congenital)\b/i,
  lactation: /\b(breast ?feeding|lactation)\b/i,
  older_adults: /\b(elderly|older (adults|people|patients)|aged (6[5-9]|[7-9]\d)|geriatric|frail)\b/i,
  children: /\b(children|child|paediatric|pediatric|infants?|neonat\w*|adolescents?|tonsillectomy)\b/i,
  renal: /\b(renal impairment|kidney disease|ckd|egfr|dialysis)\b/i,
  hepatic: /\b(hepatic impairment|cirrhosis|liver disease)\b/i,
};

const GENERIC = new Set(["drug", "drugs", "patient", "reports", "report", "label", "reaction", "reactions", "adverse reaction", "adverse reactions", "adverse event", "adverse events", "side effect", "side effects", "adverse drug reaction", "adverse effect", "risk", "known", "expected"]);
const QUESTION_WORDS = new Set(["does", "can", "is", "are", "what", "which", "why", "how", "when", "should", "will", "could", "my"]);

export interface QueryInfo {
  text: string;
  tokens: string[];
  intents: string[];
  drugs: string[];
  reactions: string[];
  populations: string[];
  dosing_request: boolean;
  primary_intent: string;
}

export function understand(text: string, drugs: Dictionary, reactions: Dictionary): QueryInfo {
  const tokens = analyse(text);
  const scores: Record<string, number> = {};
  for (const [name, pat] of Object.entries(PATTERNS)) {
    const hits = (text.match(pat) || []).length;
    if (hits) scores[name] = hits;
  }
  const drugList = drugs.mentions(text);
  for (const d of drugs.lookupNgrams(text)) if (!drugList.includes(d) && !QUESTION_WORDS.has(d)) drugList.push(d);
  const rxList = reactions.mentions(text).filter((r) => !GENERIC.has(r));
  for (const r of reactions.lookupNgrams(text)) if (!rxList.includes(r) && !drugList.includes(r) && !GENERIC.has(r)) rxList.push(r);
  if (drugList.length >= 2) scores.interaction = (scores.interaction || 0) + 2;
  if (drugList.length && rxList.length) scores.adverse_effect = (scores.adverse_effect || 0) + 1;
  if (scores.method && !drugList.length) scores.method += 2;
  const order = Object.keys(scores).sort((a, b) => scores[b] - scores[a] || INTENTS.indexOf(a) - INTENTS.indexOf(b));
  const pops = Object.entries(POP)
    .filter(([, p]) => p.test(text))
    .map(([k]) => k);
  if (pops.length && !order.includes("population")) order.push("population");
  const intents = order.length ? order : ["adverse_effect"];
  return { text, tokens, intents, drugs: drugList.slice(0, 6), reactions: rxList.slice(0, 8), populations: pops, dosing_request: DOSING.test(text), primary_intent: intents[0] };
}

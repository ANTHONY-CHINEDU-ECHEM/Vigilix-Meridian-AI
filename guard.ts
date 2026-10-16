// Port of vigilix/rag/guard.py: identifier redaction, crisis, scope, dosing and injection.

const TITLE_NAME = /\b(Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame)\.?\s+([A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+)?)/g;
const PATTERNS: [string, RegExp, string][] = [
  ["dob", /\b(?:DOB|D\.O\.B\.|date of birth|born on)[:\s]*(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?\s+\d{4})/gi, "[DOB]"],
  ["email", /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, "[EMAIL]"],
  ["nhs_number", /\b\d{3}[ -]?\d{3}[ -]?\d{4}\b/g, "[NHS_NUMBER]"],
  ["ssn", /\b\d{3}-\d{2}-\d{4}\b/g, "[ID_NUMBER]"],
  ["phone", /(?:\+44\s?7\d{3}|\b07\d{3}|\+1[\s-]?\(?\d{3}\)?)[\s-]?\d{3}[\s-]?\d{3,4}\b/g, "[PHONE]"],
  ["uk_postcode", /\b(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b/g, "[POSTCODE]"],
  ["mrn", /\b(?:MRN|hospital (?:no|number)|patient id|case id|unit number)[:#\s]*[A-Z0-9-]{4,}\b/gi, "[RECORD_ID]"],
  ["date", /\b(?:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2})\b/g, "[DATE]"],
  ["date", /\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b/gi, "[DATE]"],
];
const AGE_OVER_89 = /\b(aged?|age)\s+(9\d|1[01]\d)\b/gi;
const CRISIS =
  /\b(i\s*(?:want|am going|plan|intend)\s+to\s+(?:kill myself|end (?:my|it all)|die|overdose|take an overdose)|(?:how many|how much)\s+(?:pills|tablets|paracetamol|acetaminophen|\w+)\s+(?:would|will|does it take to)\s+(?:kill|end)|suicid\w*\s+(?:plan|note|tonight)|i(?:'m| am)\s+(?:suicidal|going to hurt myself)|want to hurt myself|self[- ]harm(?:ing)? (?:tonight|now))/i;
const OUT_OF_SCOPE =
  /\b(election|vote for|who should i vote|football|premier league|recipe|stock price|bitcoin|crypto|weather|horoscope|write (?:me )?(?:a )?(?:poem|song|essay)|python code|javascript|homework|celebrity|movie|lottery|betting odds)\b/i;
const IN_SCOPE =
  /\b(drug|medicine|medication|dose|tablet|side effect|adverse|reaction|signal|faers|label|interaction|toxicit|safety|pharmacovigilance|prescrib|vaccine|report|causality|naranjo|prr|ror|ebgm|meddra|smpc|warning|contraindicat|overdose|poison|syndrome|injury|bleeding|rash)\w*/i;
export const DOSING =
  /\b(what (?:dose|dosage)(?: of [\w ]{1,40})? (?:should|do|can) (?:i|we)|how (?:much|many)(?: [\w ]{1,30})? (?:should|do|can) (?:i|we) (?:give|take|prescribe|use)|(?:dose|dosage) for (?:my|this) (?:patient|child|baby|son|daughter)|(?:should|can) (?:i|we) (?:double|increase|halve|reduce) (?:my|the|his|her) dose|titrate .{0,30} for (?:my|this) patient|what (?:dose|dosage) (?:to|for) (?:give|prescribe))\b/i;
const INJECTION =
  /(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)|disregard (?:the )?(?:system|previous)|you are now|system prompt|act as (?:an? )?\w+ (?:that|who)|reveal (?:your|the) (?:prompt|instructions)|<\s*\/?\s*(?:system|assistant|user)\s*>|\bassistant:\s|\bsystem:\s)/gi;

export const CRISIS_MESSAGE =
  "It sounds like you might be going through something very difficult. You do not have to face it alone. In the United Kingdom you can call Samaritans free on 116 123 at any time, contact NHS 111, or call 999 if you are in immediate danger. In the United States you can call or text 988. If you have taken an overdose, please seek emergency care now, even if you feel well.";
export const SCOPE_MESSAGE =
  "Vigilix Meridian answers questions about medicine safety: adverse reactions, safety signals, drug labels, interactions and pharmacovigilance methods. This question appears to be outside that scope.";
export const DOSING_MESSAGE =
  "Vigilix Meridian does not recommend doses for individual patients. Dosing depends on the product, indication, renal and hepatic function, age, weight and co medication, and should follow the current product information and the advice of the prescriber or a pharmacist. The evidence below may still help.";

export function redact(text: string): [string, Record<string, number>] {
  const counts: Record<string, number> = {};
  let out = text;
  for (const [name, pat, repl] of PATTERNS) {
    out = out.replace(pat, () => {
      counts[name] = (counts[name] || 0) + 1;
      return repl;
    });
  }
  out = out.replace(TITLE_NAME, (_m, t) => {
    counts.name = (counts.name || 0) + 1;
    return `${t} [NAME]`;
  });
  out = out.replace(AGE_OVER_89, (_m, a) => {
    counts.age_over_89 = (counts.age_over_89 || 0) + 1;
    return `${a} over 89`;
  });
  return [out, counts];
}

export function neutralise(text: string): [string, boolean] {
  let n = 0;
  const out = text.replace(INJECTION, () => {
    n++;
    return "[instruction like text removed]";
  });
  return [out, n > 0];
}

export function check(text: string, hasEntities = false) {
  let [red, counts] = redact(text);
  const [neu, injected] = neutralise(red);
  const crisis = CRISIS.test(text);
  const oos = OUT_OF_SCOPE.test(text) && !(hasEntities || IN_SCOPE.test(text));
  return {
    redacted_text: neu,
    redactions: counts,
    crisis,
    out_of_scope: oos && !crisis,
    dosing_request: DOSING.test(text),
    injection_neutralised: injected,
  };
}

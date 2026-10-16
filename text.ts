// Line for line port of vigilix/rag/text.py. A unit test compares the outputs
// of both implementations on a shared fixture so the browser engine indexes
// and queries exactly like the Python service.

export interface Lexicon {
  spelling_rules: string[][];
  drug_synonyms: Record<string, string>;
  brands: Record<string, string>;
  abbreviations: Record<string, string>;
  lay_terms: Record<string, string>;
  stopwords: string[];
}

let LEX: Lexicon | null = null;
let REPLACE = new Map<string, string[]>();
let EXPAND = new Map<string, string[]>();
let STOP = new Set<string>();
const MAX_PHRASE = 5;
const PROTECTED = new Set(["qt", "ecg", "inr", "alt", "ast", "ck", "hiv", "covid", "sars", "sjs", "ten", "dress", "nms", "aki", "dili"]);

export function fold(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/≥/g, " >= ")
    .replace(/≤/g, " <= ");
}

export function rawTokens(text: string): string[] {
  return fold(text)
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

export function applySpelling(token: string): string {
  for (const rule of LEX!.spelling_rules) {
    const [oldS, newS, unless] = rule;
    if (token.includes(oldS) && !(unless && token.includes(unless))) token = token.split(oldS).join(newS);
  }
  return token;
}

export function initText(lex: Lexicon) {
  LEX = lex;
  REPLACE = new Map();
  EXPAND = new Map();
  const key = (p: string) => rawTokens(p).map(applySpelling);
  for (const table of ["drug_synonyms", "brands"] as const) {
    for (const [src, dst] of Object.entries(lex[table])) {
      const k = key(src);
      if (k.length && !REPLACE.has(k.join(" "))) REPLACE.set(k.join(" "), rawTokens(dst).map(applySpelling));
      else if (k.length) REPLACE.set(k.join(" "), rawTokens(dst).map(applySpelling));
    }
  }
  for (const table of ["abbreviations", "lay_terms"] as const) {
    for (const [src, dst] of Object.entries(lex[table])) {
      const k = key(src);
      const tgt = rawTokens(dst).map(applySpelling);
      if (k.length && k.join(" ") !== tgt.join(" ")) EXPAND.set(k.join(" "), tgt);
    }
  }
  STOP = new Set(lex.stopwords);
}

export function rewrite(tokens: string[]): string[] {
  const out: string[] = [];
  let i = 0;
  const n = tokens.length;
  while (i < n) {
    let matched = false;
    for (let span = Math.min(MAX_PHRASE, n - i); span > 0; span--) {
      const k = tokens.slice(i, i + span).join(" ");
      const r = REPLACE.get(k);
      if (r) {
        out.push(...r);
        i += span;
        matched = true;
        break;
      }
      const e = EXPAND.get(k);
      if (e) {
        out.push(...tokens.slice(i, i + span), ...e);
        i += span;
        matched = true;
        break;
      }
    }
    if (!matched) {
      out.push(tokens[i]);
      i += 1;
    }
  }
  return out;
}

const SUFFIXES: [string, string, number][] = [
  ["ational", "ate", 8],
  ["ization", "ize", 8],
  ["iveness", "ive", 8],
  ["fulness", "ful", 8],
  ["ousness", "ous", 8],
  ["ities", "ity", 6],
  ["ies", "y", 5],
  ["sses", "ss", 5],
  ["ings", "", 7],
  ["ing", "", 6],
  ["edly", "", 7],
  ["ed", "", 6],
  ["es", "e", 6],
  ["s", "", 5],
];

export function stem(token: string): string {
  if (/^\d+$/.test(token) || token.length <= 4 || PROTECTED.has(token)) return token;
  for (const [suffix, repl, minLen] of SUFFIXES) {
    if (token.endsWith(suffix) && token.length >= minLen) {
      if (suffix === "s" && /(ss|us|is|ys)$/.test(token)) return token;
      if (suffix === "es" && !/(ses|zes|ches|shes|xes)$/.test(token)) return token.slice(0, -1);
      return token.slice(0, token.length - suffix.length) + repl;
    }
  }
  return token;
}

export function analyse(text: string, keepStop = false): string[] {
  const toks = rewrite(rawTokens(text).map(applySpelling));
  const out: string[] = [];
  for (const t of toks) {
    if (!keepStop && STOP.has(t)) continue;
    out.push(stem(t));
  }
  return out;
}

export function canonicalDrug(name: string): string {
  const toks = rawTokens(name).map(applySpelling);
  const r = REPLACE.get(toks.join(" "));
  return r ? r.join(" ") : toks.join(" ");
}

export function canonicalTerm(name: string): string {
  const toks = rawTokens(name).map(applySpelling);
  const k = toks.join(" ");
  const e = EXPAND.get(k);
  if (e && toks.length > 1) return e.join(" ");
  const lay = LEX!.lay_terms[k];
  if (lay) return rawTokens(lay).map(applySpelling).join(" ");
  return k;
}

const NUM = /(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s?%)?/g;

function fmtG(f: number): string {
  // Python's "{:g}" formatting: up to 6 significant digits, no trailing zeros
  if (f === 0) return "0";
  const exp = Math.floor(Math.log10(Math.abs(f)));
  if (exp < -4 || exp >= 6) {
    const s = f.toExponential(5).replace(/\.?0+e/, "e");
    return s.replace(/e([+-])(\d)$/, "e$10$2");
  }
  return String(Number(f.toPrecision(6)));
}

export function numbers(text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(NUM)) {
    const v = m[0].replace(/,/g, "").replace(/ /g, "").replace(/%$/, "");
    const f = Number(v);
    if (!Number.isNaN(f)) out.push(fmtG(f));
  }
  return out;
}

export function sentences(text: string): string[] {
  text = text.replace(/\s+/g, " ").trim();
  if (!text) return [];
  const parts = text.split(/(?<=[.!?])\s+(?=[A-Z0-9(\[])/);
  const merged: string[] = [];
  for (const p of parts) {
    if (merged.length && (p.length < 25 || /\b(?:vs|e\.g|i\.e|approx|no|fig|ref|et al)\.$/i.test(merged[merged.length - 1]))) merged[merged.length - 1] += " " + p;
    else merged.push(p);
  }
  return merged;
}

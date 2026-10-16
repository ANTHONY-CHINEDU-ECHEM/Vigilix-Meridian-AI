import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { analyse, canonicalDrug, canonicalTerm, initText, numbers } from "./text";
import { score } from "./stats";
import { naranjo, whoUmc } from "./causality";
import { check } from "./guard";

const lex = JSON.parse(readFileSync(new URL("../../public/data/lexicon.json", import.meta.url), "utf8"));
const fixture = JSON.parse(readFileSync(new URL("../../public/data/parity_fixture.json", import.meta.url), "utf8"));
initText(lex);

describe("TypeScript normaliser matches the Python implementation", () => {
  for (const f of fixture) {
    it(f.text, () => {
      expect(analyse(f.text)).toEqual(f.analyse);
      expect(numbers(f.text)).toEqual(f.numbers);
      expect(canonicalDrug(f.text.split(" ")[0])).toEqual(f.drug);
      expect(canonicalTerm(f.text.split(";")[0])).toEqual(f.term);
    });
  }
});

describe("disproportionality port", () => {
  it("matches reference values computed in Python", () => {
    const prior = { alpha1: 0.846944, beta1: 0.064777, alpha2: 1.395996, beta2: 0.946748, p: 0.255951 };
    const r = score(20, 980, 400, 200000, prior);
    expect(r.prr).toBeCloseTo(10.02, 2);
    expect(r.ror).toBeCloseTo(10.2041, 3);
    expect(r.ic025).toBeCloseTo(2.2368, 3);
    expect(r.ebgm).toBeCloseTo(9.254, 2);
    expect(r.eb05).toBeCloseTo(6.1487, 2);
    expect(r.signal_votes).toBe(4);
  });
});

describe("causality and guard ports", () => {
  it("scores Naranjo categories", () => {
    expect(naranjo({ after_drug: "yes", improved_on_stop: "yes", reappeared_on_rechallenge: "yes", alternative_causes: "no", objective_evidence: "yes", previous_reports: "yes" }).category).toBe("definite");
    expect(naranjo({}).category).toBe("doubtful");
    expect(whoUmc("yes", "no", "yes", "unknown", "yes").category).toBe("probable");
  });
  it("redacts identifiers and flags crisis language", () => {
    const g = check("Mr John Smith, NHS 943 476 5919, DOB 03/04/1957 had a rash on lamotrigine");
    expect(g.redacted_text).not.toContain("943 476");
    expect(g.redactions.name).toBe(1);
    expect(check("I want to kill myself tonight").crisis).toBe(true);
  });
});

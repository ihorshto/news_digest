import { describe, expect, it } from "vitest";
import { validateAuth, validateTopic } from "./validation";
import { t, plural } from "../i18n/uk";

describe("validateAuth", () => {
  it("accepts valid credentials", () => {
    expect(validateAuth("a@b.co", "password123", "register", "password123")).toEqual({});
  });

  it("rejects bad email and short password on register", () => {
    const errors = validateAuth("nope", "short", "register", "short");
    expect(errors.email).toBe(t.auth.errors.emailInvalid);
    expect(errors.password).toBe(t.auth.errors.passwordShort);
  });

  it("does not enforce length on login", () => {
    expect(validateAuth("a@b.co", "x", "login")).toEqual({});
  });

  it("detects mismatched confirmation", () => {
    expect(validateAuth("a@b.co", "password123", "register", "password124").confirm).toBe(
      t.auth.errors.passwordMismatch,
    );
  });
});

describe("validateTopic", () => {
  it("requires name and description", () => {
    expect(validateTopic(" ", "ab")).toEqual({
      name: t.topic.errors.nameRequired,
      description: t.topic.errors.descriptionShort,
    });
  });
});

describe("plural", () => {
  it("handles Ukrainian plural forms", () => {
    expect(plural(1, "новина", "новини", "новин")).toBe("новина");
    expect(plural(3, "новина", "новини", "новин")).toBe("новини");
    expect(plural(11, "новина", "новини", "новин")).toBe("новин");
    expect(plural(25, "новина", "новини", "новин")).toBe("новин");
  });
});

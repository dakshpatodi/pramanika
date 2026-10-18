import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";

import { getApiErrorMessage } from "@/lib/errors";

const FALLBACK = "We couldn't do that. Please try again.";

describe("getApiErrorMessage", () => {
  it("surfaces the message of a plain Error", () => {
    expect(getApiErrorMessage(new Error("boom"), FALLBACK)).toBe("boom");
    expect(getApiErrorMessage(new Error("Server down"), FALLBACK)).toBe("Server down");
  });

  it("uses the fallback when the error has no useful message", () => {
    expect(getApiErrorMessage(new Error(""), FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage(new Error("   "), FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage(null, FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage("just a string", FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage({ message: "not an Error" }, FALLBACK)).toBe(FALLBACK);
  });

  it("does not leak axios' generic text when the server sent no message", () => {
    const err = new AxiosError("Request failed with status code 500", "ERR_BAD_RESPONSE");
    expect(getApiErrorMessage(err, FALLBACK)).toBe(FALLBACK);
  });
});

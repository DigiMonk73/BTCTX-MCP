// @vitest-environment jsdom
// A link pressed before what it goes to is on the page still gets there,
// once it's shown (#612), but not after a press long forgotten.
import { afterEach, describe, expect, it, vi } from "vitest";
import { whenShown } from "./whenShown";

function add(id: string): HTMLElement {
  const element = document.createElement("h2");
  element.id = id;
  document.body.appendChild(element);
  return element;
}

// MutationObserver's callbacks run as a microtask after the change
const settled = () => new Promise((done) => setTimeout(done, 0));

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("whenShown", () => {
  it("goes at once to an element already on the page", () => {
    const title = add("price-card-title");
    const then = vi.fn();
    whenShown("price-card-title", then);
    expect(then).toHaveBeenCalledExactlyOnceWith(title);
  });

  it("waits for one not shown yet, and goes there once, when it is", async () => {
    const then = vi.fn();
    whenShown("price-card-title", then);
    add("something-else");
    await settled();
    expect(then).not.toHaveBeenCalled();
    const title = add("price-card-title");
    await settled();
    add("price-card-title-2");
    await settled();
    expect(then).toHaveBeenCalledExactlyOnceWith(title);
  });

  it("finds it inside what's added, as a card brings its title", async () => {
    const then = vi.fn();
    whenShown("price-card-title", then);
    const card = document.createElement("section");
    card.innerHTML = '<h2 id="price-card-title">Bitcoin prices</h2>';
    document.body.appendChild(card);
    await settled();
    expect(then).toHaveBeenCalledExactlyOnceWith(card.firstElementChild);
  });

  it("gives up after the wait", async () => {
    vi.useFakeTimers();
    const then = vi.fn();
    whenShown("price-card-title", then, 5_000);
    vi.advanceTimersByTime(5_000);
    vi.useRealTimers();
    add("price-card-title");
    await settled();
    expect(then).not.toHaveBeenCalled();
  });
});

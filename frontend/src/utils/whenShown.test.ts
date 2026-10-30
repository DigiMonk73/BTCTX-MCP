// @vitest-environment jsdom
// A link pressed before what it goes to is on the page still gets there,
// once it's shown (#612), but not after a press long forgotten, nor once
// the user has gone on to another page or control.
import { afterEach, describe, expect, it, vi } from "vitest";
import { whenShown } from "./whenShown";

function add(id: string, tag = "h2"): HTMLElement {
  const element = document.createElement(tag);
  element.id = id;
  document.body.appendChild(element);
  return element;
}

/** The link, pressed: it has the keyboard. */
function pressed(): HTMLElement {
  const link = add("choose-a-source", "a");
  link.setAttribute("href", "#price-card-title");
  link.focus();
  return link;
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
    whenShown("price-card-title", pressed(), then);
    expect(then).toHaveBeenCalledExactlyOnceWith(title);
  });

  it("waits for one not shown yet, and goes there once, when it is", async () => {
    const then = vi.fn();
    whenShown("price-card-title", pressed(), then);
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
    const page = add("the-page", "main");
    whenShown("price-card-title", pressed(), then);
    const card = document.createElement("section");
    card.innerHTML = '<h2 id="price-card-title">Bitcoin prices</h2>';
    page.appendChild(card);
    await settled();
    expect(then).toHaveBeenCalledExactlyOnceWith(card.firstElementChild);
  });

  it("still goes there when the press left the keyboard on nothing, as a click in Safari does", async () => {
    const link = pressed();
    link.blur();
    const then = vi.fn();
    whenShown("price-card-title", link, then);
    const title = add("price-card-title");
    await settled();
    expect(then).toHaveBeenCalledExactlyOnceWith(title);
  });

  it("gives up after the wait", async () => {
    vi.useFakeTimers();
    const then = vi.fn();
    whenShown("price-card-title", pressed(), then);
    vi.advanceTimersByTime(5_000);
    vi.useRealTimers();
    add("price-card-title");
    await settled();
    expect(then).not.toHaveBeenCalled();
  });

  it("doesn't once the user has gone to another page, which has a price card of its own", async () => {
    const link = pressed();
    const then = vi.fn();
    whenShown("price-card-title", link, then);
    link.remove();
    add("price-card-title");
    await settled();
    expect(then).not.toHaveBeenCalled();
  });

  it("doesn't once the keyboard is on another control", async () => {
    const link = pressed();
    const then = vi.fn();
    whenShown("price-card-title", link, then);
    add("amount", "input").focus();
    add("price-card-title");
    await settled();
    expect(then).not.toHaveBeenCalled();
  });
});

// Add Transaction's Date & Time shows the whole date and time (#755): in a
// column of the drawer's two, Chromium's date-and-time with seconds lost its
// month ("/01/2026, 10:15:30 AM"). The field is as wide as the same input
// left to size itself to its fields, at a desktop window, the Mac app's
// smallest (800 x 600) and a phone's.
import { test, expect, openAddForm } from "./fixtures";

const SIZES = [
  { name: "a desktop window", width: 1280, height: 900 },
  { name: "the Mac app's smallest window", width: 800, height: 600 },
  { name: "a phone", width: 390, height: 844 },
];

for (const size of SIZES) {
  test(`Date & Time shows the whole date and time at ${size.name} (#755)`, async ({ authedPage: page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openAddForm(page, "Transfer");
    const date = page.getByLabel("Date & Time");
    await date.fill("2026-03-01T10:15:30");
    const [width, needs] = await date.evaluate((el) => {
      const copy = el.cloneNode() as HTMLInputElement;
      copy.value = (el as HTMLInputElement).value;
      copy.style.cssText = "width: auto; position: absolute; visibility: hidden";
      el.parentElement!.appendChild(copy);
      const natural = copy.getBoundingClientRect().width;
      copy.remove();
      return [el.getBoundingClientRect().width, natural];
    });
    expect(width).toBeGreaterThanOrEqual(needs);
  });
}

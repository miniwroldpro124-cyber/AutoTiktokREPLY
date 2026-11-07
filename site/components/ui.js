"use client";

export function Card({ title, right, children, className = "" }) {
  return (
    <section className={"card " + className}>
      {(title || right) && (
        <div className="card-h">
          <h3>{title}</h3>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Toggle({ on, onChange, disabled }) {
  return (
    <button
      type="button"
      className={"sw" + (on ? " on" : "")}
      disabled={disabled}
      aria-pressed={!!on}
      onClick={() => onChange(!on)}
    >
      <i />
    </button>
  );
}

export function Btn({ variant = "", children, ...rest }) {
  return (
    <button type="button" className={"btn " + variant} {...rest}>
      {children}
    </button>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      {label && <span className="lab">{label}</span>}
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

export function Seg({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button
          key={o.v}
          className={value === o.v ? "on" : ""}
          onClick={() => onChange(o.v)}
        >
          {o.l}
        </button>
      ))}
    </div>
  );
}

export function lineClass(line) {
  if (/\[(OK|REPLY)\]/.test(line)) return "lg-ok";
  if (/\[(FAIL|ERR)\]/.test(line)) return "lg-fail";
  if (/\[(WARN|SKIP|COOLDOWN)\]/.test(line)) return "lg-warn";
  if (/\[(INFO|auto-send)\]/.test(line)) return "lg-info";
  return "lg-dim";
}

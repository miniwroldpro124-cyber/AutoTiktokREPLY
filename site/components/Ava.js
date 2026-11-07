"use client";

import { useState } from "react";

export default function Ava({ src, name = "", size = 26, className = "" }) {
  const [bad, setBad] = useState(false);
  const initial = (name || "?").replace(/^@/, "").charAt(0).toUpperCase();
  const style = {
    width: size,
    height: size,
    fontSize: Math.max(10, Math.round(size * 0.45)),
  };
  if (src && !bad) {
    return (
      <img
        className={"ava " + className}
        style={style}
        src={src}
        alt=""
        onError={() => setBad(true)}
      />
    );
  }
  return (
    <span className={"ava ava-fb " + className} style={style}>
      {initial}
    </span>
  );
}

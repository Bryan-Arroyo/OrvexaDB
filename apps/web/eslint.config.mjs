import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default [
  { ignores: ["node_modules/**", ".next/**", "coverage/**", "test-results/**", "next-env.d.ts"] },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    rules: {
      // Los cargadores async actualizan estado tras completar la petición.
      "react-hooks/set-state-in-effect": "off",
      "@next/next/no-location-assign-relative-destination": "off",
    },
  },
];

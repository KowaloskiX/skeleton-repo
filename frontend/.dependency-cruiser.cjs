/** Frontend module boundaries — see docs/conventions/05-architecture-enforcement.md */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Cycles between modules are forbidden.",
      from: {},
      to: { circular: true },
    },
    {
      name: "feature-isolation",
      severity: "error",
      comment: "features/* import each other only through the public index.ts.",
      from: { path: "^src/features/([^/]+)/" },
      to: { path: "^src/features/(?!$1)[^/]+/(?!index\\.ts$)" },
    },
    {
      name: "ui-kit-knows-nothing-about-features",
      severity: "error",
      comment:
        "components/ui holds stateless design primitives. Importing a feature from there " +
        "means the component is in the wrong directory — it belongs in features/<name>/.",
      from: { path: "^src/components/" },
      to: { path: "^src/(features|routes)/" },
    },
    {
      name: "generated-api-client-is-private",
      severity: "error",
      comment:
        "The OpenAPI client is generated — consume it via src/lib/api/index.ts, not file by file.",
      from: { pathNot: "^src/lib/api/" },
      to: { path: "^src/lib/api/(?!index\\.ts$)" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    exclude: { path: "routeTree\\.gen\\.ts$" },
    tsConfig: { fileName: "tsconfig.json" },
  },
};

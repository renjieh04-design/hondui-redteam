# Configuration migrations

## Versioned evaluation rule references

`evaluation_rule_refs` is a breaking configuration change. A rule reference is
now an object containing an exact rule identifier and version; the former plain
string form is rejected because it cannot reproduce the rule used by a run.

Before:

```yaml
evaluation_rule_refs:
  - privacy-check
```

After:

```yaml
evaluation_rule_refs:
  - rule_id: privacy-check
    version: "1.0"
```

The version must be resolved before `TaskDefinition` is built. `latest` and `*`
are not valid stored versions.

# Design Principles

- Repository policy enters through configuration or injected adapters.
- Rendering remains deterministic for fixed inputs.
- Check mode performs no source write.
- Write mode validates the complete selection before replacing any managed block.
- Each file replacement is atomic.
- An ordinary replacement failure restores files replaced earlier in the run.
- Core modules do not import a consuming repository's paths, task syntax, or manifests.

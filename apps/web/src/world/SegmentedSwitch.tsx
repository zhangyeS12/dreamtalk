import styles from "./SegmentedSwitch.module.css";

/** A small pill of mutually exclusive choices, e.g. the chat display mode. */
export function SegmentedSwitch<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: ReadonlyArray<{ value: T; label: string }>; onChange: (value: T) => void;
}) {
  return <div className={styles.segmented} role="group" aria-label={label}>
    {options.map(option => <button key={option.value} type="button" aria-pressed={option.value === value}
      onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

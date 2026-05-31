import React from 'react';
import { useId } from 'react';
import { cn } from '../../utils/cn';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, className = '', id, ...props }, ref) => {
    const generatedId = useId();
    const textareaId = id ?? props.name ?? generatedId;
    const hintId = hint ? `${textareaId}-hint` : undefined;
    const errorId = error ? `${textareaId}-error` : undefined;
    const describedBy = [props['aria-describedby'], errorId ?? hintId].filter(Boolean).join(' ') || undefined;
    const ariaInvalid = props['aria-invalid'] ?? (error ? true : undefined);

    const textareaStyle = error
      ? {
          ...props.style,
          ['--input-surface-border-focus' as string]: 'hsla(var(--destructive), 0.4)',
          ['--input-surface-focus-ring' as string]: '0 0 0 4px hsla(var(--destructive), 0.1)',
        }
      : props.style;

    return (
      <div className="flex flex-col">
        {label ? (
          <label
            htmlFor={textareaId}
            className="mb-2 text-sm font-medium text-foreground"
          >
            {label}
          </label>
        ) : null}
        <textarea
          id={textareaId}
          aria-describedby={describedBy}
          aria-invalid={ariaInvalid}
          style={textareaStyle}
          ref={ref}
          className={cn(
            'input-surface input-focus-glow min-h-[80px] w-full rounded-lg border bg-transparent px-3 py-2 text-sm transition-all',
            'focus:outline-none focus:ring-2',
            error ? 'border-danger/30' : '',
            'disabled:cursor-not-allowed disabled:opacity-60',
            'resize-y',
            className,
          )}
          {...props}
        />
        {error ? (
          <p
            id={errorId}
            role="alert"
            className="mt-2 text-xs text-danger"
          >
            {error}
          </p>
        ) : hint ? (
          <p
            id={hintId}
            className="mt-2 text-xs text-secondary-text"
          >
            {hint}
          </p>
        ) : null}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';

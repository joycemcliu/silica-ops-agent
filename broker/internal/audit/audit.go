// Package audit emits one redacted JSON object for each broker tool call.
package audit

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"sync"
	"time"

	"ops-agent/broker/internal/redact"
)

// Arguments must contain only request data, never authentication headers or
// credential references. Raw output is never written to the audit stream.
type Event struct {
	Time       time.Time `json:"time"`
	Who        string    `json:"who"`
	Session    string    `json:"session"`
	Env        string    `json:"env"`
	Tool       string    `json:"tool"`
	Arguments  any       `json:"arguments"`
	ResultSize int       `json:"result_size"`
	DurationMS int64     `json:"duration_ms"`
	Error      string    `json:"error,omitempty"`
}

type Writer struct {
	out      io.Writer
	redactor *redact.Redactor
	mu       sync.Mutex
}

func New(out io.Writer, redactor *redact.Redactor) (*Writer, error) {
	if out == nil || redactor == nil {
		return nil, errors.New("audit output and redactor are required")
	}
	return &Writer{out: out, redactor: redactor}, nil
}

func (w *Writer) Write(event Event) error {
	if event.Time.IsZero() {
		event.Time = time.Now().UTC()
	}
	// Sanitize decoded string values BEFORE encoding. Redacting serialized JSON
	// can corrupt its syntax or miss credentials that JSON escapes.
	data, err := json.Marshal(event)
	if err != nil {
		return errors.New("cannot encode audit event")
	}
	var decoded any
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err = decoder.Decode(&decoded); err != nil {
		return errors.New("cannot decode audit event")
	}
	clean := scrub(decoded, w.redactor)
	data, err = json.Marshal(clean)
	if err != nil {
		return errors.New("cannot encode sanitized audit event")
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	data = append(data, '\n')
	n, err := w.out.Write(data)
	if err != nil || n != len(data) {
		return errors.New("audit write failed")
	}
	return nil
}

func scrub(value any, redactor *redact.Redactor) any {
	switch v := value.(type) {
	case string:
		return redactor.String(v)
	case []any:
		for i := range v {
			v[i] = scrub(v[i], redactor)
		}
	case map[string]any:
		for key, item := range v {
			// Contextual patterns need the field name for e.g. {"password":"x"}.
			if redactor.String(key+"=audit-field-sentinel") != key+"=audit-field-sentinel" {
				v[key] = redact.Replacement
			} else {
				v[key] = scrub(item, redactor)
			}
		}
		clean := make(map[string]any, len(v))
		for key, item := range v {
			clean[redactor.String(key)] = item
		}
		return clean
	}
	return value
}

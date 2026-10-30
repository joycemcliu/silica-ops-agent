package audit

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"

	"ops-agent/broker/internal/redact"
)

func TestStructuredRedactedEvent(t *testing.T) {
	r, _ := redact.New(nil)
	r.AddSecret("synthetic\"escaped\ncredential")
	var out bytes.Buffer
	w, err := New(&out, r)
	if err != nil {
		t.Fatal(err)
	}
	err = w.Write(Event{Who: "operator", Session: "test-session", Env: "test-a", Tool: "run_readonly", Arguments: map[string]any{
		"argv": []string{"cat", "synthetic\"escaped\ncredential"}, "password": "synthetic-raw", "token": 1234,
		"nested": map[string]any{"email": "operator@example.invalid"},
	}, ResultSize: 10, DurationMS: 5, Error: "password=synthetic-error"})
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Count(out.Bytes(), []byte("\n")) != 1 {
		t.Fatal("event is not one JSON line")
	}
	for _, forbidden := range []string{"synthetic", "example.invalid", "1234"} {
		if strings.Contains(out.String(), forbidden) {
			t.Fatalf("audit leaked %s", forbidden)
		}
	}
	var event map[string]any
	if err := json.Unmarshal(out.Bytes(), &event); err != nil {
		t.Fatal(err)
	}
	if event["env"] != "test-a" || event["result_size"] != float64(10) {
		t.Fatal(event)
	}
}

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, errors.New("synthetic-sensitive-error") }

type shortWriter struct{}

func (shortWriter) Write([]byte) (int, error) { return 0, nil }

func TestErrorsAreSafe(t *testing.T) {
	r, _ := redact.New(nil)
	if _, err := New(nil, r); err == nil {
		t.Fatal("nil sink accepted")
	}
	if _, err := New(&bytes.Buffer{}, nil); err == nil {
		t.Fatal("nil redactor accepted")
	}
	for _, sink := range []interface{ Write([]byte) (int, error) }{failedWriter{}, shortWriter{}} {
		w, _ := New(sink, r)
		if err := w.Write(Event{}); err == nil || strings.Contains(err.Error(), "synthetic-sensitive") {
			t.Fatal(err)
		}
	}
	w, _ := New(&bytes.Buffer{}, r)
	if err := w.Write(Event{Arguments: make(chan int)}); err == nil {
		t.Fatal("unsupported JSON accepted")
	}
}

func TestConcurrentEventsAreWholeJSONLines(t *testing.T) {
	r, _ := redact.New(nil)
	var out bytes.Buffer
	w, _ := New(&out, r)
	var wg sync.WaitGroup
	for range 30 {
		wg.Go(func() {
			if err := w.Write(Event{Tool: "whoami"}); err != nil {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	if len(lines) != 30 {
		t.Fatal("lost or duplicate events")
	}
	for _, line := range lines {
		if !json.Valid([]byte(line)) {
			t.Fatal("interleaved event")
		}
	}
}

func TestNumericArgumentsPreservePrecision(t *testing.T) {
	r, _ := redact.New(nil)
	var out bytes.Buffer
	w, _ := New(&out, r)
	const identifier int64 = 9007199254740993
	if err := w.Write(Event{Arguments: map[string]any{"id": identifier}}); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "9007199254740993") {
		t.Fatal("audit changed the argument value", out.String())
	}
}

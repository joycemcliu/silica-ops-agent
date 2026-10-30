// Package config provides strict, bounded YAML decoding for broker configuration.
package config

import (
	"bytes"
	"errors"
	"io"

	"go.yaml.in/yaml/v3"
)

const MaxBytes = 1 << 20

// Decode refuses unknown fields, duplicate keys, trailing documents and large
// input. Parser errors are deliberately not returned: they can echo secret data.
func Decode(r io.Reader, dst any) error {
	data, err := io.ReadAll(io.LimitReader(r, MaxBytes+1))
	if err != nil || len(data) > MaxBytes {
		return errors.New("configuration unreadable or too large")
	}
	dec := yaml.NewDecoder(bytes.NewReader(data))
	dec.KnownFields(true)
	if err := dec.Decode(dst); err != nil {
		return errors.New("invalid configuration: check fields, types and duplicate keys")
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return errors.New("configuration must contain exactly one YAML document")
	}
	return nil
}

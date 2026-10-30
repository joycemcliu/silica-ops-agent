package config

import (
	"strings"
	"testing"
)

func TestStrictDecode(t *testing.T) {
	for _, input := range []string{"", "null", "known: x\nextra: y", "known: x\nknown: y", "known: x\n---\nknown: y", strings.Repeat("x", MaxBytes+1)} {
		t.Run(input[:min(len(input), 40)], func(t *testing.T) {
			var value struct {
				Known string `yaml:"known"`
			}
			err := Decode(strings.NewReader(input), &value)
			// null is a valid document; domain loaders validate required fields.
			if err == nil && input != "null" {
				t.Fatal("invalid document accepted")
			}
		})
	}
}

func TestParserErrorsDoNotEchoInput(t *testing.T) {
	var value struct {
		Port int `yaml:"port"`
	}
	err := Decode(strings.NewReader("port: secret-synthetic"), &value)
	if err == nil || strings.Contains(err.Error(), "secret-synthetic") {
		t.Fatal("unsafe parser error", err)
	}
}

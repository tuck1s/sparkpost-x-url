# Sparkpost-x-url

Extends the SparkPost template language with external data-source accesses, for example

Nested expressions are allowed, the intention is to allow replacement of any part of the request e.g.
```
   {{x-url get https://blah.com?{{foo}}
   {{x-url get https://blah.com?{{foo.{{bar}} }}
   {{x-url {{foo}} }}
```
and even have a url return a url e.g.
```
   {{x-url {{x-url {{foo}} }} }}
```

Substitution variable values within the expression e.g. `{{foo}}` are read with precedence

- Per-recipient `substitution_data`
- Per-recipient `metadata`
- Global (transmission level) `substitution_data`
- Global (transmission level) `metadata`

Template making example use of [OneSpot](https://www.onespot.com/) content personalisation service is included in [heml](https://heml.io) format.

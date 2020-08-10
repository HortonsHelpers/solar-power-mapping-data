# Directory structure

`as_received`

: Datasets precisely in the form in which we originally got them, unchanged in
  content or format, whether text or binary, open or proprietary.

`raw`

: Data that has been manually edited, at least to change the format to one that
  we can use programmatically (if required) but also there may a small number of
  edits to the data that do not seem to be generalisable, or we can't work out
  how to automate, or are not likely to re-occur next time we download the data.

`processed`

: Datasets that have been programmatically modified (typically from `raw`). Note
  that the `processed` directory is _local_, it is like a “compiled code”
  directory: not under version control but neither on the shared drive.


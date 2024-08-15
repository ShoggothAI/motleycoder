(equals_assignment
    (identifier) @name
    (function_definition) @definition.function
) @definition.function

(left_assignment
    (identifier) @name
    (function_definition) @definition.function
) @definition.function

(call
    function: (identifier) @name
) @reference.call

(call
    function: (binary
        left: (identifier)
        right: (identifier) @name
    )
) @reference.call

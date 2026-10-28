#include <stddef.h>

#define TUTOR_ALLOCATION_LIMIT 1024

typedef struct {
    void *address;
    size_t size;
    int is_freed;
} TutorAllocation;

TutorAllocation tutor_allocations[TUTOR_ALLOCATION_LIMIT];
size_t tutor_alloc_count;
int tutor_tracking_enabled;

void *__real_malloc(size_t size);
void *__real_calloc(size_t count, size_t size);
void *__real_realloc(void *address, size_t size);
void __real_free(void *address);

static void tutor_record_allocation(void *address, size_t size) {
    if (address == NULL || tutor_alloc_count >= TUTOR_ALLOCATION_LIMIT) {
        return;
    }
    tutor_allocations[tutor_alloc_count].address = address;
    tutor_allocations[tutor_alloc_count].size = size;
    tutor_allocations[tutor_alloc_count].is_freed = 0;
    tutor_alloc_count++;
}

static void tutor_mark_freed(void *address) {
    size_t i = tutor_alloc_count;
    while (i > 0) {
        TutorAllocation *allocation = &tutor_allocations[--i];
        if (allocation->address == address && !allocation->is_freed) {
            allocation->is_freed = 1;
            return;
        }
    }
}

void *__wrap_malloc(size_t size) {
    void *address = __real_malloc(size);
    if (tutor_tracking_enabled) {
        tutor_record_allocation(address, size);
    }
    return address;
}

void *__wrap_calloc(size_t count, size_t size) {
    void *address = __real_calloc(count, size);
    if (tutor_tracking_enabled && (count == 0 || size <= (size_t)-1 / count)) {
        tutor_record_allocation(address, count * size);
    }
    return address;
}

void *__wrap_realloc(void *old_address, size_t size) {
    void *new_address = __real_realloc(old_address, size);
    if (tutor_tracking_enabled && (new_address != NULL || size == 0)) {
        tutor_mark_freed(old_address);
        tutor_record_allocation(new_address, size);
    }
    return new_address;
}

void __wrap_free(void *address) {
    if (tutor_tracking_enabled) {
        tutor_mark_freed(address);
    }
    __real_free(address);
}

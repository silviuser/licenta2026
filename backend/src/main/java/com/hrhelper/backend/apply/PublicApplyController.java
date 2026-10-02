package com.hrhelper.backend.apply;

import com.hrhelper.backend.apply.PublicApplyService.ApplyStatus;
import com.hrhelper.backend.apply.dto.PublicApplyResponse;
import com.hrhelper.backend.apply.dto.PublicJobView;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * Public, unauthenticated candidate apply endpoint (REWORK 3 D32/D34/D35). Mapped
 * under {@code /api/public/**}, which Spring Security permits without a JWT. A
 * generic 404 hides whether a token ever existed or is merely disabled (D38).
 */
@RestController
@RequestMapping("/api/public/apply/{token}")
public class PublicApplyController {

    private final PublicApplyService publicApplyService;

    public PublicApplyController(PublicApplyService publicApplyService) {
        this.publicApplyService = publicApplyService;
    }

    @GetMapping
    public PublicJobView job(@PathVariable String token) {
        return publicApplyService.getJobView(token);
    }

    /**
     * Multipart submission. Fields are optional at the binding layer so a missing
     * field surfaces as a clean 400 from validation rather than a 500.
     */
    @PostMapping
    public ResponseEntity<PublicApplyResponse> apply(
            @PathVariable String token,
            @RequestParam(value = "name", required = false) String name,
            @RequestParam(value = "email", required = false) String email,
            @RequestParam(value = "phone", required = false) String phone,
            @RequestParam(value = "file", required = false) MultipartFile file) {
        ApplyStatus status = publicApplyService.apply(token, name, email, phone, file);
        if (status == ApplyStatus.RECEIVED) {
            return ResponseEntity.status(HttpStatus.CREATED).body(PublicApplyResponse.received());
        }
        return ResponseEntity.ok(PublicApplyResponse.updated());
    }
}
